from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import uuid
import logging
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
import secrets

# Configuración
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Tunnel Relay Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@dataclass
class TunnelClient:
    websocket: WebSocket
    client_id: str
    subdomain: str
    last_heartbeat: float
    is_active: bool = True

@dataclass
class TunnelRequest:
    request_id: str
    method: str
    url: str
    headers: Dict
    body: bytes
    client_id: str
    created_at: float
    response_queue: asyncio.Queue

class TunnelManager:
    def __init__(self):
        self.clients: Dict[str, TunnelClient] = {}
        self.subdomain_map: Dict[str, str] = {}  # subdomain -> client_id
        self.requests: Dict[str, TunnelRequest] = {}
        self.request_timeout = 30.0  # 30 seconds timeout

    def generate_client_id(self) -> str:
        return secrets.token_urlsafe(16)

    async def register_client(self, websocket: WebSocket, subdomain: str = None) -> str:
        client_id = self.generate_client_id()
        
        if not subdomain:
            subdomain = client_id[:8]
        
        # Ensure subdomain is unique
        counter = 1
        original_subdomain = subdomain
        while subdomain in self.subdomain_map:
            subdomain = f"{original_subdomain}-{counter}"
            counter += 1
        
        client = TunnelClient(
            websocket=websocket,
            client_id=client_id,
            subdomain=subdomain,
            last_heartbeat=time.time()
        )
        
        self.clients[client_id] = client
        self.subdomain_map[subdomain] = client_id
        
        logger.info(f"Client registered: {client_id} with subdomain: {subdomain}")
        return client_id, subdomain

    def remove_client(self, client_id: str):
        if client_id in self.clients:
            client = self.clients[client_id]
            if client.subdomain in self.subdomain_map:
                del self.subdomain_map[client.subdomain]
            del self.clients[client_id]
            logger.info(f"Client removed: {client_id}")

    def get_client_by_subdomain(self, subdomain: str) -> Optional[TunnelClient]:
        if subdomain in self.subdomain_map:
            client_id = self.subdomain_map[subdomain]
            return self.clients.get(client_id)
        return None

    async def create_request(self, client_id: str, method: str, url: str, headers: Dict, body: bytes) -> Optional[TunnelRequest]:
        if client_id not in self.clients:
            return None
        
        request_id = str(uuid.uuid4())
        response_queue = asyncio.Queue()
        
        request = TunnelRequest(
            request_id=request_id,
            method=method,
            url=url,
            headers=headers,
            body=body,
            client_id=client_id,
            created_at=time.time(),
            response_queue=response_queue
        )
        
        self.requests[request_id] = request
        return request

    def cleanup_expired_requests(self):
        current_time = time.time()
        expired_requests = []
        
        for request_id, request in self.requests.items():
            if current_time - request.created_at > self.request_timeout:
                expired_requests.append(request_id)
        
        for request_id in expired_requests:
            del self.requests[request_id]
            logger.info(f"Expired request cleaned up: {request_id}")

    async def send_request_to_client(self, request: TunnelRequest) -> bool:
        if request.client_id not in self.clients:
            return False
        
        client = self.clients[request.client_id]
        
        try:
            request_data = {
                "type": "request",
                "request_id": request.request_id,
                "method": request.method,
                "url": request.url,
                "headers": dict(request.headers),
                "body": request.body.decode('latin1') if request.body else None
            }
            
            await client.websocket.send_text(json.dumps(request_data))
            return True
        except Exception as e:
            logger.error(f"Error sending request to client: {e}")
            return False

    async def wait_for_response(self, request_id: str) -> Optional[Dict]:
        if request_id not in self.requests:
            return None
        
        request = self.requests[request_id]
        
        try:
            response_data = await asyncio.wait_for(
                request.response_queue.get(), 
                timeout=self.request_timeout
            )
            return response_data
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for response: {request_id}")
            return None
        finally:
            if request_id in self.requests:
                del self.requests[request_id]

    def handle_client_response(self, request_id: str, response_data: Dict):
        if request_id in self.requests:
            request = self.requests[request_id]
            request.response_queue.put_nowait(response_data)

# Global tunnel manager
tunnel_manager = TunnelManager()

# Background task to cleanup expired requests
async def cleanup_task():
    while True:
        await asyncio.sleep(60)  # Cleanup every minute
        tunnel_manager.cleanup_expired_requests()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_task())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = None
    
    try:
        # Initial handshake
        data = await websocket.receive_text()
        handshake = json.loads(data)
        
        if handshake.get("type") != "register":
            await websocket.close(code=1008, reason="Invalid handshake")
            return
        
        subdomain = handshake.get("subdomain")
        client_id, assigned_subdomain = await tunnel_manager.register_client(websocket, subdomain)
        
        # Send registration confirmation
        await websocket.send_text(json.dumps({
            "type": "registered",
            "client_id": client_id,
            "subdomain": assigned_subdomain
        }))
        
        # Heartbeat loop
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                message = json.loads(data)
                
                if message.get("type") == "heartbeat":
                    # Update last heartbeat
                    if client_id in tunnel_manager.clients:
                        tunnel_manager.clients[client_id].last_heartbeat = time.time()
                    await websocket.send_text(json.dumps({"type": "heartbeat_ack"}))
                
                elif message.get("type") == "response":
                    # Handle response from client
                    request_id = message.get("request_id")
                    tunnel_manager.handle_client_response(request_id, message)
                
            except asyncio.TimeoutError:
                # Send heartbeat to check connection
                try:
                    await websocket.send_text(json.dumps({"type": "heartbeat"}))
                except:
                    break  # Connection lost
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if client_id:
            tunnel_manager.remove_client(client_id)

@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def tunnel_proxy(request: Request, full_path: str, background_tasks: BackgroundTasks):
    # Extract subdomain from host
    host = request.headers.get("host", "")
    subdomain = host.split(".")[0] if host and "." in host else None
    
    if not subdomain:
        return JSONResponse(
            {"error": "No subdomain specified"}, 
            status_code=400
        )
    
    # Find client by subdomain
    client = tunnel_manager.get_client_by_subdomain(subdomain)
    if not client or not client.is_active:
        return JSONResponse(
            {"error": "Tunnel not found or inactive"}, 
            status_code=404
        )
    
    # Read request body
    body = await request.body()
    
    # Create tunnel request
    tunnel_request = await tunnel_manager.create_request(
        client.client_id,
        request.method,
        str(request.url),
        dict(request.headers),
        body
    )
    
    if not tunnel_request:
        return JSONResponse(
            {"error": "Failed to create tunnel request"}, 
            status_code=500
        )
    
    # Send request to client
    if not await tunnel_manager.send_request_to_client(tunnel_request):
        return JSONResponse(
            {"error": "Failed to send request to client"}, 
            status_code=503
        )
    
    # Wait for response from client
    response_data = await tunnel_manager.wait_for_response(tunnel_request.request_id)
    
    if not response_data:
        return JSONResponse(
            {"error": "Timeout waiting for response from client"}, 
            status_code=504
        )
    
    # Extract response details
    status_code = response_data.get("status_code", 500)
    headers = response_data.get("headers", {})
    body = response_data.get("body", "")
    
    # Convert body back to bytes if it's a string
    if isinstance(body, str):
        body = body.encode('latin1')
    
    # Create response
    return StreamingResponse(
        iter([body]),
        status_code=status_code,
        headers=headers
    )

@app.get("/health")
async def health_check():
    return {"status": "ok", "clients": len(tunnel_manager.clients)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
