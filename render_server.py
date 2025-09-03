from fastapi import FastAPI, Request, Header
from fastapi.responses import StreamingResponse
from asyncio import Queue

app = FastAPI()

# Cola por archivo
file_queues = {}  # {path: Queue()}

@app.get("/poll")
async def poll():
    # Devuelve el siguiente path a procesar
    for path, q in file_queues.items():
        if not q.empty():
            return path
    return ""

@app.post("/send_chunk")
async def send_chunk(request: Request, x_path: str = Header(...)):
    """Recibe un chunk para un archivo específico"""
    chunk = await request.body()
    if x_path not in file_queues:
        file_queues[x_path] = Queue()
    await file_queues[x_path].put(chunk)
    return {"status": "ok"}

@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    if full_path not in file_queues:
        file_queues[full_path] = Queue()

    async def generator():
        q = file_queues[full_path]
        while True:
            chunk = await q.get()
            if not chunk:  # Fin de archivo
                break
            yield chunk

    return StreamingResponse(generator(), media_type="application/octet-stream")
