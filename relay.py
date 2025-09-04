import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import aiohttp

app = FastAPI()

client_ws: WebSocket | None = None
ws_lock = asyncio.Lock()  # Bloquea acceso a client_ws


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Mantiene vivo el WebSocket con el bot local"""
    global client_ws
    await websocket.accept()
    async with ws_lock:
        client_ws = websocket
    print("[+] Bot local conectado al relay")

    try:
        while True:
            await asyncio.sleep(15)  # heartbeat
            try:
                await websocket.send_bytes(b"__PING__")
            except:
                break
    except WebSocketDisconnect:
        print("[!] Bot local desconectado")
    finally:
        async with ws_lock:
            client_ws = None


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    """Recibe solicitudes externas y las reenvía al bot local"""
    global client_ws

    async with ws_lock:
        if client_ws is None:
            return {"error": "No hay cliente conectado"}

        # Normaliza query string
        query = str(request.url.query).replace("?", "&")
        full_path = f"/{path}"
        if query:
            full_path += f"?{query}"

        body = await request.body()
        msg = json.dumps({
            "method": request.method,
            "path": full_path,
            "headers": dict(request.headers),
            "body": body.decode("utf-8", errors="ignore")
        })

        # Enviar solicitud al bot local
        await client_ws.send_text(msg)

    async def stream_response():
        """Recibe chunks desde el bot local y los envía al cliente HTTP"""
        try:
            while True:
                try:
                    # Timeout evita que quede bloqueado si el bot falla
                    data = await asyncio.wait_for(client_ws.receive_bytes(), timeout=30)
                except asyncio.TimeoutError:
                    print("[!] Timeout esperando datos del bot local")
                    break
                if data == b"__END__":
                    break
                yield data
        except WebSocketDisconnect:
            print("[!] Bot local desconectado durante streaming")
            yield b""
        except Exception as e:
            print(f"[!] Error streaming: {e}")
            yield b""

    return StreamingResponse(stream_response())
