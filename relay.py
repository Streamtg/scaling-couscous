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
        while True:
            await asyncio.sleep(10)  # Mantener conexión
    except WebSocketDisconnect:
        client_ws = None

@app.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    global client_ws
    if client_ws is None:
        return {"error": "No hay cliente conectado"}

    query = f"?{request.url.query}" if request.url.query else ""
    body = await request.body()

    msg = json.dumps({
        "method": request.method,
        "path": "/" + path + query,
        "body": body.decode(errors="ignore") if body else ""
    })

    # Enviar al cliente
    await client_ws.send_text(msg)

    async def stream_response():
        try:
            while True:
                chunk = await client_ws.receive_bytes()
                if chunk == b"__END__":
                    break
                yield chunk
        except Exception as e:
            print(f"[!] Error streaming: {e}")
            yield b""

    # Streaming directo
    return StreamingResponse(stream_response(), media_type="application/octet-stream")
