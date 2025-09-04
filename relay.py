from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()

# Guardamos el WebSocket del cliente local
client_ws: WebSocket = None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global client_ws
    await websocket.accept()
    client_ws = websocket
    try:
        while True:
            await websocket.receive_text()  # Mantener viva la conexión
    except WebSocketDisconnect:
        client_ws = None

@app.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    global client_ws
    if client_ws is None:
        return {"error": "No hay cliente conectado"}

    # Preparamos la petición para el cliente
    body = await request.body()
    msg = json.dumps({
        "method": request.method,
        "path": "/" + path,
        "headers": dict(request.headers),
        "body": body.decode("utf-8", errors="ignore")
    })

    # Enviamos la petición al cliente
    await client_ws.send_text(msg)

    # Esperamos la respuesta en chunks
    async def stream_response():
        try:
            while True:
                data = await client_ws.receive_bytes()
                if data == b"__END__":
                    break
                yield data
        except Exception:
            yield b""

    return StreamingResponse(stream_response())
