from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import uuid
import os

app = FastAPI()

# Diccionario de buffers para cada request activo
active_buffers = {}
request_queue = asyncio.Queue()

@app.get("/poll")
async def poll():
    """
    Devuelve el siguiente path pendiente para la máquina local.
    Si no hay nada, devuelve string vacío.
    """
    try:
        path = request_queue.get_nowait()
        return {"path": path}
    except asyncio.QueueEmpty:
        return {"path": ""}

@app.post("/poll")
async def post_chunk(request: Request):
    """
    Recibe chunks de datos desde la máquina local
    y los coloca en el buffer correspondiente.
    """
    request_id = request.headers.get("X-Request-ID")
    if not request_id or request_id not in active_buffers:
        raise HTTPException(status_code=400, detail="Invalid Request ID")

    data = await request.body()
    await active_buffers[request_id].put(data)
    return {"status": "ok"}

@app.get("/{full_path:path}")
async def stream_proxy(full_path: str):
    """
    Endpoint público para exponer el recurso solicitado.
    Genera un stream asincrónico hacia el cliente.
    """
    request_id = str(uuid.uuid4())
    await request_queue.put(full_path)
    buffer = asyncio.Queue()
    active_buffers[request_id] = buffer

    async def generator():
        while True:
            chunk = await buffer.get()
            if chunk == b"__END__":
                break
            yield chunk
        # Limpiar buffer activo al finalizar
        del active_buffers[request_id]

    return StreamingResponse(
        generator(),
        media_type="application/octet-stream",
        headers={"X-Request-ID": request_id}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
