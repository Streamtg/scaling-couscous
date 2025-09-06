from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio, json, uuid, logging
from typing import Dict, Optional
from datetime import datetime

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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.client_ws: Optional[WebSocket] = None
        self.queues: Dict[str, asyncio.Queue] = {}
        self.last_heartbeat: Optional[datetime] = None
    
    async def connect(self, websocket: WebSocket):
        self.client_ws = websocket
        self.last_heartbeat = datetime.now()
        logger.info("[+] Cliente local conectado")
    
    def disconnect(self):
        self.client_ws = None
        self.last_heartbeat = None
        logger.info("[!] Cliente desconectado")
    
    async def send_message(self, message: str):
        if self.client_ws:
            try:
                await self.client_ws.send_text(message)
                return True
            except Exception as e:
                logger.error(f"Error enviando mensaje: {e}")
                return False
        return False
    
    def is_connected(self):
        return self.client_ws is not None and (
            self.last_heartbeat is None or 
            (datetime.now() - self.last_heartbeat).total_seconds() < 30
        )

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await manager.connect(websocket)
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=30.0)
                
                if data.get("type") == "websocket.receive":
                    text_data = data.get("text")
                    if text_data:
                        try:
                            message = json.loads(text_data)
                            if message.get("type") == "heartbeat":
                                manager.last_heartbeat = datetime.now()
                                await websocket.send_text(json.dumps({"type": "heartbeat_ack"}))
                            elif message.get("type") == "client_ready":
                                logger.info(f"Cliente listo, path: {message.get('path')}")
                        except json.JSONDecodeError:
                            logger.warning("Mensaje no JSON recibido")
                
            except asyncio.TimeoutError:
                # Verificar conexión
                if not manager.is_connected():
                    logger.warning("Heartbeat timeout, cerrando conexión")
                    break
                continue
                
    except WebSocketDisconnect:
        logger.info("[!] Cliente WebSocket desconectado")
    except Exception as e:
        logger.error(f"[!] Error en WebSocket: {e}")
    finally:
        manager.disconnect()

@app.get("/stream/{file_id}")
async def stream_file(file_id: str, request: Request):
    """Endpoint principal de streaming"""
    if not manager.is_connected():
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
    
    # Crear queue para esta solicitud
    manager.queues[req_id] = asyncio.Queue()
    
    if not await manager.send_message(message):
        del manager.queues[req_id]
        raise HTTPException(status_code=503, detail="Error comunicando con cliente")

    async def generate_chunks():
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(manager.queues[req_id].get(), timeout=120.0)
                    if chunk == b"__END__":
                        logger.info(f"Stream completado para {req_id}")
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

    # Configurar headers para streaming
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "Transfer-Encoding": "chunked"
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
    await manager.queues[req_id].put(data)
    
    return {"ok": True, "size": len(data)}

@app.get("/health")
async def health_check():
    """Endpoint de health check"""
    status = {
        "status": "ok" if manager.is_connected() else "no_client",
        "client_connected": manager.is_connected(),
        "last_heartbeat": manager.last_heartbeat.isoformat() if manager.last_heartbeat else None,
        "active_streams": len(manager.queues)
    }
    return status

@app.get("/")
async def root():
    """Página de inicio"""
    return {
        "message": "Streaming Relay Server",
        "status": "online",
        "client_connected": manager.is_connected()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
