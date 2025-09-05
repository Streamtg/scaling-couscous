from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import asyncio, json, uuid

app = FastAPI()
client_ws: WebSocket = None
queues = {}  # diccionario por request id

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

@app.api_route("/{path:path}", methods=["GET"])
async def proxy(path: str, request: Request):
    global client_ws
    if client_ws is None:
        return {"error": "No hay cliente conectado"}

    req_id = str(uuid.uuid4())
    body = await request.body()
    range_header = request.headers.get("range")

    msg = json.dumps({
        "id": req_id,
        "method": request.method,
        "path": "/" + path + ("?" + request.url.query if request.url.query else ""),
        "headers": dict(request.headers),
        "body": body.decode("utf-8", errors="ignore"),
        "range": range_header
    })

    queues[req_id] = asyncio.Queue()
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

    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "video/mp4"
    }

    status_code = 200
    # Si hay Range → 206 Partial Content
    if range_header:
        # Parsear Range: "bytes=start-end"
        try:
            _, range_val = range_header.split("=")
            start_str, end_str = range_val.split("-")
            start = int(start_str)
            end = int(end_str) if end_str else None
        except Exception:
            start = 0
            end = None
        headers["Content-Range"] = f"bytes {start}-{end or ''}/{{fileSize}}"  # fileSize lo llenará el cliente
        status_code = 206

    return StreamingResponse(
        stream_response(),
        status_code=status_code,
        headers=headers
    )
