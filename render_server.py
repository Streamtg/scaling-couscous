from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import asyncio

app = FastAPI()

# Diccionario de buffers para cada request
response_buffers = {}
request_queue = asyncio.Queue()

@app.get("/poll")
async def poll():
    """Devuelve el siguiente path pendiente para la máquina local"""
    try:
        path = request_queue.get_nowait()
        return path
    except asyncio.QueueEmpty:
        return ""

@app.post("/poll")
async def poll_post(request: Request):
    """Recibe chunks desde la máquina local"""
    data = await request.body()
    request_id = request.headers.get("X-Request-ID")
    if request_id in response_buffers:
        await response_buffers[request_id].put(data)
    return {"status": "ok"}

@app.get("/{full_path:path}")
async def proxy(full_path: str):
    """Recibe request pública y devuelve streaming asincrónico"""
    import uuid
    request_id = str(uuid.uuid4())
    await request_queue.put(full_path)
    buffer = asyncio.Queue()
    response_buffers[request_id] = buffer

    async def stream_generator():
        while True:
            chunk = await buffer.get()
            if chunk == b"__END__":
                break
            yield chunk
        del response_buffers[request_id]

    return StreamingResponse(stream_generator(), media_type="application/octet-stream", headers={"X-Request-ID": request_id})
