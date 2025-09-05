from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse, Response
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

    # Enviamos al cliente las cabeceras incluyendo Range si viene
    msg = json.dumps({
        "method": request.method,
        "path": "/" + path + query,
        "headers": dict(request.headers),
        "body": body.decode(errors="ignore") if body else ""
    })

    await client_ws.send_text(msg)

    first_chunk = {"data": None, "headers": {}}

    async def stream_response():
        try:
            while True:
                data = await client_ws.receive_bytes()
                if data.startswith(b"__HEADERS__"):
                    # El cliente envía metadatos de respuesta
                    hdrs = json.loads(data.decode().replace("__HEADERS__", "", 1))
                    first_chunk["headers"] = hdrs
                    continue
                if data == b"__END__":
                    break
                if first_chunk["data"] is None:
                    first_chunk["data"] = data
                yield data
        except Exception as e:
            print(f"[!] Error streaming: {e}")
            yield b""

    headers = first_chunk["headers"]
    status_code = 206 if "Content-Range" in headers else 200
    return StreamingResponse(stream_response(), status_code=status_code, headers=headers)
