from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()

client_ws: WebSocket = None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global client_ws
    await websocket.accept()
    client_ws = websocket
    try:
        # Mantener vivo el socket
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        client_ws = None


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    global client_ws
    if client_ws is None:
        return {"error": "No hay cliente conectado"}

    body = await request.body()
    msg = json.dumps({
        "method": request.method,
        "path": "/" + path + ("?" + request.url.query if request.url.query else ""),
        "headers": dict(request.headers),
        "body": body.decode("utf-8", errors="ignore")
    })

    # Enviamos la solicitud al cliente local
    await client_ws.send_text(msg)

    async def stream_response():
        try:
            while True:
                data = await client_ws.receive_bytes()
                if data == b"__END__":
                    break
                # 🔑 Entregamos los bytes en tiempo real
                yield data
        except Exception as e:
            print(f"[!] Error streaming: {e}")
            yield b""

    # 🔑 Usar transferencia chunked para evitar buffering
    return StreamingResponse(
        stream_response(),
        media_type="application/octet-stream",
        headers={
            "Transfer-Encoding": "chunked",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
