from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()
client_ws: WebSocket = None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Mantiene conexión WebSocket con el cliente (túnel local).
    """
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
    """
    Recibe peticiones HTTP del bot y las envía al túnel.
    Stream real de datos hacia Render.
    """
    global client_ws
    if not client_ws:
        return {"error": "No hay cliente conectado"}

    # Construir mensaje
    query_string = f"?{request.url.query}" if request.url.query else ""
    body = await request.body()
    msg = json.dumps({
        "method": request.method,
        "path": "/" + path + query_string,
        "headers": dict(request.headers),
        "body": body.decode("utf-8", errors="ignore")
    })

    # Enviar al túnel
    await client_ws.send_text(msg)

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

    return StreamingResponse(stream_response(), media_type="application/octet-stream")
