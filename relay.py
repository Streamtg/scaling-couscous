# relay_fastapi.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()

# WebSocket global para un cliente Render
client_ws: WebSocket = None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global client_ws
    await websocket.accept()
    client_ws = websocket
    print("[+] Render conectado via WebSocket")
    try:
        while True:
            await asyncio.sleep(10)  # heartbeat para mantener vivo el socket
    except WebSocketDisconnect:
        client_ws = None
        print("[!] Render desconectado")

@app.api_route("/{full_path:path}", methods=["GET", "POST"])
async def proxy(full_path: str, request: Request):
    """
    Proxy para redirigir requests del relay Render al bot local.
    Maneja query params y streaming en chunks.
    """
    global client_ws
    if client_ws is None:
        return {"error": "No hay cliente Render conectado"}

    # Reconstruir path completo con query params
    query_string = str(request.url.query)
    path = f"/{full_path}"
    if query_string:
        path += f"?{query_string}"

    # Leer body si existe
    body = await request.body()
    body_text = body.decode("utf-8", errors="ignore")

    # Preparar mensaje JSON para Render
    msg = json.dumps({
        "method": request.method,
        "path": path,
        "headers": dict(request.headers),
        "body": body_text
    })

    # Enviar mensaje al cliente Render
    await client_ws.send_text(msg)

    # Función generadora de streaming
    async def stream_response():
        try:
            while True:
                data = await client_ws.receive_bytes()
                if data == b"__END__":
                    break
                yield data
        except Exception as e:
            print(f"[!] Error streaming: {e}")
            yield b""

    return StreamingResponse(stream_response())
