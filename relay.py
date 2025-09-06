from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio, json, uuid, logging
from typing import Dict, Optional

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.client_ws: Optional[WebSocket] = None
        self.queues: Dict[str, asyncio.Queue] = {}
    
    async def connect(self, websocket: WebSocket):
        self.client_ws = websocket
        logger.info("[+] Cliente local conectado")
    
    def disconnect(self):
        self.client_ws = None
        logger.info("[!] Cliente desconectado")
    
    async def send_message(self, message: str):
        if self.client_ws:
            await self.client_ws.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await manager.connect(websocket)
    
    try:
        while True:
            # Real heartbeat - esperar mensajes del cliente
            data = await websocket.receive()
            if data.get("type") == "websocket.disconnect":
                break
            # También podemos recibir chunks de datos aquí si es necesario
    except WebSocketDisconnect:
        logger.info("[!] Cliente WebSocket desconectado")
    except Exception as e:
        logger.error(f"[!] Error en WebSocket: {e}")
    finally:
        manager.disconnect()

@app.get("/stream/{file_id}")
async def stream_file(file_id: str, request: Request):
    """Endpoint principal de streaming"""
    if manager.client_ws is None:
        raise HTTPException(status_code=503, detail="No hay cliente conectado")

    req_id = str(uuid.uuid4())
    range_header = request.headers.get("range")
    
    # Enviar solicitud al cliente local
    message = json.dumps({
        "type": "stream_request",
        "id": req_id,
        "file_id": file_id,
        "range": range_header
    })
    
    try:
        # Crear queue para esta solicitud
        manager.queues[req_id] = asyncio.Queue()
        await manager.send_message(message)
        
        # Timeout para esperar respuesta
        await asyncio.wait_for(manager.queues[req_id].get(), timeout=30.0)
        
    except asyncio.TimeoutError:
        if req_id in manager.queues:
            del manager.queues[req_id]
        raise HTTPException(status_code=504, detail="Timeout esperando respuesta del cliente")

    async def generate_chunks():
        try:
            while True:
                # Esperar chunks con timeout
                try:
                    chunk = await asyncio.wait_for(manager.queues[req_id].get(), timeout=60.0)
                    if chunk == b"__END__":
                        break
                    yield chunk
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout esperando chunk para {req_id}")
                    break
        except Exception as e:
            logger.error(f"Error en generador de chunks: {e}")
        finally:
            # Limpiar
            if req_id in manager.queues:
                del manager.queues[req_id]

    # Configurar headers apropiados para streaming
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",  # Ajustar según tipo de archivo
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
    }

    return StreamingResponse(
        generate_chunks(),
        media_type="video/mp4",
        headers=headers
    )

@app.post("/push/{req_id}")
async def push_chunk(req_id: str, request: Request):
    """Cliente local envía chunks aquí"""
    if req_id not in manager.queues:
        return JSONResponse({"error": "request_id inválido"}, status_code=404)
    
    data = await request.body()
    if data == b"__END__":
        await manager.queues[req_id].put(b"__END__")
    else:
        await manager.queues[req_id].put(data)
    
    return {"ok": True, "size": len(data)}

@app.get("/health")
async def health_check():
    """Endpoint de health check"""
    return {"status": "ok", "client_connected": manager.client_ws is not None}
