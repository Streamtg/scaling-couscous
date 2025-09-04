# app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import asyncio
import os
import json

app = FastAPI()
clients = {}  # Diccionario para múltiples conexiones WebSocket
CHUNK_SIZE = 64 * 1024  # 64KB por chunk

# ----------------------------
# WebSocket endpoint (Render)
# ----------------------------
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    clients[client_id] = websocket
    print(f"[+] Render conectado: {client_id}")
    try:
        while True:
            await asyncio.sleep(10)  # mantener vivo el socket
    except WebSocketDisconnect:
        clients.pop(client_id, None)
        print(f"[!] Render desconectado: {client_id}")

# ----------------------------
# Proxy de archivos locales
# ----------------------------
@app.api_route("/{full_path:path}", methods=["GET", "POST"])
async def proxy(full_path: str, request: Request):
    client_id = request.headers.get("X-Client-ID")
    if not client_id or client_id not in clients:
        return {"error": "No hay cliente Render conectado o X-Client-ID no definido"}

    websocket = clients[client_id]

    # Reconstruir path con query params
    query_string = str(request.url.query)
    path = f"/{full_path}"
    if query_string:
        path += f"?{query_string}"

    # Preparar mensaje JSON para Render
    body = await request.body()
    msg = json.dumps({
        "method": request.method,
        "path": path,
        "headers": dict(request.headers),
        "body": body.decode("utf-8", errors="ignore")
    })
    await websocket.send_text(msg)

    # Stream incremental desde archivo local o WebSocket
    async def stream_response():
        local_path = full_path.lstrip("/")  # Ajusta según tu estructura
        if os.path.isfile(local_path):
            try:
                with open(local_path, "rb") as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        await websocket.send(chunk)
                        yield chunk
                await websocket.send(b"__END__")
            except Exception as e:
                print(f"[!] Error streaming archivo {local_path}: {e}")
                yield b""
        else:
            # Esperar streaming desde WebSocket si el archivo no existe local
            try:
                while True:
                    data = await websocket.receive_bytes()
                    if data == b"__END__":
                        break
                    yield data
            except Exception as e:
                print(f"[!] Error streaming desde WebSocket: {e}")
                yield b""

    return StreamingResponse(stream_response())
