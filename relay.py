from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import asyncio, json, uuid, time

app = FastAPI()

# un websocket por cliente
clients = {}          # id -> WebSocket
streams   = {}        # req_id -> asyncio.Queue

# ---------- 1.  websocket de control ----------
@app.websocket("/ws")
async def ctrl_ws(websocket: WebSocket):
    await websocket.accept()
    cid = str(uuid.uuid4())
    clients[cid] = websocket
    print("[+] cliente local conectado", cid)
    try:
        while True:
            # heartbeat + limpieza de colas vacías
            await websocket.receive_text()
    except WebSocketDisconnect:
        print("[-] cliente local desconectado", cid)
        clients.pop(cid, None)

# ---------- 2.  petición del navegador ----------
@app.get("/stream/{file_id}")
async def stream(file_id: str, request: Request):
    if not clients:
        return StreamingResponse(status_code=503)

    req_id = str(uuid.uuid4())
    rng = request.headers.get("range", "")
    start, end = 0, ""
    if rng:
        try:
            a, b = rng.replace("bytes=", "").split("-")
            start = int(a) if a else 0
            end   = int(b) if b else ""
        except Exception:
            pass

    # pedimos al cliente local que abra el fichero
    msg = json.dumps({"id": req_id, "file_id": file_id,
                      "range": rng, "client": list(clients.keys())[0]})
    ws = next(iter(clients.values()))
    await ws.send_text(msg)

    # cola donde recibiremos los chunks
    q = asyncio.Queue(maxsize=50)
    streams[req_id] = q

    async def gen():
        try:
            while True:
                chunk = await q.get()
                if chunk == b"__END__":
                    break
                yield chunk
        finally:
            streams.pop(req_id, None)

    headers = {"Accept-Ranges": "bytes"}
    status  = 206 if rng else 200
    if rng and end:
        headers["Content-Range"] = f"bytes {start}-{end}/*"
    return StreamingResponse(gen(), status_code=status, headers=headers)

# ---------- 3.  el cliente local sube chunks ----------
@app.post("/push/{req_id}")
async def push(req_id: str, request: Request):
    if req_id not in streams:
        return {"error": "gone"}
    data = await request.body()
    await streams[req_id].put(data)
    return {"ok": True}
