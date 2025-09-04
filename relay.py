from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()
client_ws = None
CHUNK_SIZE = 64 * 1024

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global client_ws
    await websocket.accept()
    client_ws = websocket
    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        client_ws = None

@app.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    global client_ws
    if not client_ws:
        return {"error": "No hay cliente conectado"}

    # Mensaje a enviar al túnel local
    body = await request.body()
    msg = json.dumps({
        "method": request.method,
        "path": "/" + path + ("?" + request.url.query if request.url.query else ""),
        "headers": dict(request.headers),
        "body": body.decode("utf-8", errors="ignore")
    })
    await client_ws.send_text(msg)

    # Stream de respuesta
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
