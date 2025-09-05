# relay_render.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio, json, uuid

app = FastAPI()
client_ws: WebSocket = None
queues = {}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global client_ws
    await websocket.accept()
    client_ws = websocket
    print("[+] Cliente local conectado")
    try:
        while True:
            await asyncio.sleep(10)  # heartbeat
    except WebSocketDisconnect:
        print("[!] Cliente desconectado")
        client_ws = None

@app.get("/stream/{file_id}")
async def stream_file(file_id: str, request: Request):
    """Endpoint principal de streaming con fallback"""
    global client_ws
    if client_ws is None:
        return JSONResponse({"error": "No hay cliente conectado"}, status_code=503)

    req_id = str(uuid.uuid4())
    range_header = request.headers.get("range")

    # mandar al cliente local
    msg = json.dumps({
        "id": req_id,
        "file_id": file_id,
        "range": range_header
    })
    queues[req_id] = asyncio.Queue()
    await client_ws.send_text(msg)

    async def iterfile():
        try:
            while True:
                chunk = await queues[req_id].get()
                if chunk == b"__END__":
                    break
                yield chunk
        except Exception as e:
            print(f"[!] Error en iterfile: {e}")
            yield b""
        finally:
            queues.pop(req_id, None)

    headers = {"Accept-Ranges": "bytes"}
    status_code = 200
    if range_header:
        headers["Content-Range"] = f"bytes */*"
        status_code = 206

    return StreamingResponse(iterfile(), status_code=status_code, headers=headers)

@app.post("/push/{req_id}")
async def push_chunk(req_id: str, request: Request):
    """Cliente local envía chunks aquí como fallback HTTP"""
    if req_id not in queues:
        return JSONResponse({"error": "request_id inválido"}, status_code=404)
    data = await request.body()
    if data == b"__END__":
        await queues[req_id].put(b"__END__")
    else:
        await queues[req_id].put(data)
    return {"ok": True}
