from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio

app = FastAPI()

# Cola de paths enviados por los clientes
request_queue = asyncio.Queue()

# Cola de chunks enviados desde clientes locales
chunk_queues = {}

@app.get("/poll")
async def poll():
    """
    La máquina local hace polling para obtener paths pendientes
    """
    try:
        path = request_queue.get_nowait()
        return JSONResponse(content={"path": path})
    except asyncio.QueueEmpty:
        return JSONResponse(content={"path": ""})

@app.post("/push/{path:path}")
async def push(path: str, request: Request):
    """
    La máquina local envía chunks de datos al servidor
    """
    body = await request.body()
    if path not in chunk_queues:
        chunk_queues[path] = asyncio.Queue()
    await chunk_queues[path].put(body)
    return JSONResponse(content={"status": "ok"})

@app.get("/{path:path}")
async def stream_file(path: str):
    """
    Servir los datos enviados por la máquina local como StreamingResponse
    """
    if path not in chunk_queues:
        chunk_queues[path] = asyncio.Queue()

    async def generator():
        while True:
            chunk = await chunk_queues[path].get()
            yield chunk

    # streaming de tipo binario
    return StreamingResponse(generator(), media_type="application/octet-stream")

@app.get("/")
async def root():
    return JSONResponse(content={"status": "running"})

if __name__ == "__main__":
    import os, uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
