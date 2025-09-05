from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import asyncio
import json
from typing import Dict

app = FastAPI()

client_ws: WebSocket = None
queues: Dict[str, asyncio.Queue] = {}  # una cola por request_id

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global client_ws
    await websocket.accept()
    client_ws = websocket
    print("[+] Cliente local conectado")

    try:
        while True:
            # 🔑 recibir chunks centralizado
            data = await websocket.receive_bytes()
            # Primeros 36 bytes reservados para el request_id
            req_id = data[:36].decode("utf-8", errors="ignore")
            chunk = data[36:]

            if req_id in queues:
                await queues[req_id].put(chunk)
    except WebSocketDisconnect:
        print("[!] Cliente desconectado")
        client_ws = None


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    global client_ws
    if client_ws is None:
        return {"error": "No hay cliente conectado"}

    # 🔑 request_id único
    import uuid
    req_id = str(uuid.uuid4())

    body = await request.body()
    msg = json.dumps({
        "id": req_id,
        "method": request.method,
        "path": "/" + path + ("?" + request.url.query if request.url.query else ""),
        "headers": dict(request.headers),
        "body": body.decode("utf-8", errors="ignore")
    })

    # preparar cola para este request
    queues[req_id] = asyncio.Queue()

    # enviar al cliente local
    await client_ws.send_text(msg)

    async def stream_response():
        try:
            while True:
                chunk = await queues[req_id].get()
                if chunk == b"__END__":
                    break
                yield chunk
        except Exception as e:
            print(f"[!] Error streaming: {e}")
            yield b""
        finally:
            del queues[req_id]

    return StreamingResponse(
        stream_response(),
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
