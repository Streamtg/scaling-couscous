from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio
import json
import uuid
import struct
import os

app = FastAPI()
clients = {}  # Diccionario de clientes WebSocket: {client_id: WebSocket}
queues = {}  # Colas para chunks: {req_id: Queue}
metadata_events = {}  # Eventos para metadata: {req_id: Event}
metadata_dict = {}  # Metadata: {req_id: dict}

async def receive_task(client_id: str, websocket: WebSocket):
    while True:
        try:
            message = await websocket.receive_bytes()
            if not message:
                continue

            msg_type = message[0]
            id_len = struct.unpack('>I', message[1:5])[0]
            pos = 5
            req_id = message[pos:pos + id_len].decode('utf-8')
            pos += id_len

            if msg_type == 0:  # metadata
                data_len = struct.unpack('>I', message[pos:pos + 4])[0]
                pos += 4
                data = message[pos:pos + data_len].decode('utf-8')
                meta = json.loads(data)
                if req_id in metadata_dict:
                    metadata_dict[req_id] = meta
                    metadata_events[req_id].set()

            elif msg_type == 1:  # chunk
                chunk_len = struct.unpack('>I', message[pos:pos + 4])[0]
                pos += 4
                chunk = message[pos:pos + chunk_len]
                if req_id in queues:
                    await queues[req_id].put(chunk)

            elif msg_type == 2:  # end
                if req_id in queues:
                    await queues[req_id].put(b"__END__")

        except Exception as e:
            print(f"[!] Error en receive_task para {client_id}: {e}")
            break

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    clients[client_id] = websocket
    print(f"[+] Cliente {client_id} conectado")

    recv_task = asyncio.create_task(receive_task(client_id, websocket))

    try:
        while True:
            await asyncio.sleep(10)  # heartbeat
    except WebSocketDisconnect:
        print(f"[!] Cliente {client_id} desconectado")
        clients.pop(client_id, None)
        recv_task.cancel()

@app.get("/stream/{file_id}")
async def stream_file(file_id: str, request: Request):
    if not clients:
        return JSONResponse({"error": "No hay clientes conectados"}, status_code=503)

    req_id = str(uuid.uuid4())
    range_header = request.headers.get("range")

    queues[req_id] = asyncio.Queue()
    metadata_events[req_id] = asyncio.Event()
    metadata_dict[req_id] = {}

    # Enviar solicitud a todos los clientes
    msg = json.dumps({
        "id": req_id,
        "file_id": file_id,
        "range": range_header
    })
    disconnected = []
    for client_id, ws in clients.items():
        try:
            await ws.send_text(msg)
        except Exception:
            disconnected.append(client_id)

    for client_id in disconnected:
        clients.pop(client_id, None)

    # Esperar metadata de cualquier cliente
    try:
        await asyncio.wait_for(metadata_events[req_id].wait(), timeout=10)
    except asyncio.TimeoutError:
        queues.pop(req_id, None)
        metadata_events.pop(req_id, None)
        metadata_dict.pop(req_id, None)
        return JSONResponse({"error": "Timeout esperando metadata"}, status_code=504)

    meta = metadata_dict[req_id]
    status_code = 200
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(meta["content_length"])
    }
    if range_header:
        status_code = 206
        headers["Content-Range"] = f"bytes {meta['start']}-{meta['end']}/{meta['total_size']}"

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
            metadata_events.pop(req_id, None)
            metadata_dict.pop(req_id, None)

    return StreamingResponse(
        iterfile(),
        status_code=status_code,
        headers=headers,
        media_type=meta["content_type"]
    )

@app.post("/push/{req_id}")
async def push_chunk(req_id: str, request: Request):
    if req_id not in queues:
        return JSONResponse({"error": "request_id inválido"}, status_code=404)
    data = await request.body()
    if data == b"__END__":
        await queues[req_id].put(b"__END__")
    else:
        await queues[req_id].put(data)
    return {"ok": True}
