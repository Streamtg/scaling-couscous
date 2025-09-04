from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import aiohttp

app = FastAPI()

LOCAL_CLIENT = "http://localhost:5000"  # cliente en tu PC

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    async with aiohttp.ClientSession() as session:
        async with session.request(
            method=request.method,
            url=f"{LOCAL_CLIENT}/{path}",
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            data=await request.body()
        ) as resp:
            return StreamingResponse(
                resp.content,
                status_code=resp.status,
                headers=dict(resp.headers)
            )
