from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import aiohttp

app = FastAPI()

LOCAL_SERVER = "http://localhost:8080"  # se reemplaza dinámicamente por el cliente

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str):
    async with aiohttp.ClientSession() as session:
        async with session.request(
            method=request.method,
            url=f"{LOCAL_SERVER}/{path}",
            headers={k: v for k, v in request.headers.items() if k != "host"},
            data=await request.body()
        ) as resp:
            return StreamingResponse(
                resp.content,
                status_code=resp.status,
                headers=dict(resp.headers)
            )
