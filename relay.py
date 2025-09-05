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
            await asyncio.sleep(10)  # heartbeat
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
        "body": body.decode(errors="ignore")
    })

    # Enviar al cliente inmediatamente
    await client_ws.send_text(msg)

    async def stream_response():
        try:
            while True:
                # Recibir chunk desde el cliente
                chunk = await client_ws.receive_bytes()
                if chunk == b"__END__":
                    break
                if chunk:
                    yield chunk
        except Exception as e:
            print(f"[!] Error en streaming: {e}")
            yield b""

    return StreamingResponse(stream_response(), media_type="application/octet-stream")
