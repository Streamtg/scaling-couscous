# app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import asyncio
import os
import json

app = FastAPI()
client_ws: WebSocket = None
CHUNK_SIZE = 64 * 1024  # 64KB por chunk

# ----------------------------
# WebSocket endpoint (Render)
# ----------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global client_ws
    await websocket.accept()
    client_ws = websocket
    print("[+] Render conectado via WebSocket")
    try:
        while True:
            await asyncio.sleep(10)  # mantener vivo el socket
    except WebSocketDisconnect:
        client_ws = None
        print("[!] Render desconectado")

# ----------------------------
# Proxy de archivos locales
# ----------------------------
@app.api_route("/{full_path:path}", methods=["GET", "POST"])
async def proxy(full_path: str, request: Request):
    global client_ws
    if client_ws is None:
        return {"error": "No hay cliente Render conectado"}

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
    await client_ws.send_text(msg)

    # Stream incremental desde archivo local
    async def stream_response():
        local_path = full_path.lstrip("/")  # Ajusta según tu estructura
        if os.path.isfile(local_path):
            try:
                with open(local_path, "rb") as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        await client_ws.send(chunk)
                        yield chunk
                await client_ws.send(b"__END__")
            except Exception as e:
                print(f"[!] Error streaming archivo {local_path}: {e}")
                yield b""
        else:
            # Esperar streaming desde WebSocket si el archivo no existe local
            try:
                while True:
                    data = await client_ws.receive_bytes()
                    if data == b"__END__":
                        break
                    yield data
            except Exception as e:
                print(f"[!] Error streaming desde WebSocket: {e}")
                yield b""

    return StreamingResponse(stream_response())
