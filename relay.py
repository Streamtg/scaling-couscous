from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import httpx, os, uuid

app = FastAPI()
TG_TOKEN   = os.getenv("5471483205:AAHOgy6y5LzxOJJ42znF4Kr_SfaW7Ic9oFc")          # botfather
LOCAL_URL  = os.getenv("https://streammgram.onrender.com")         # https://tu-tunel.ngrok.io

@app.get("/stream/{file_id}")
async def stream(file_id: str, request: Request):
    """
    file_id puede ser:
      - file_unique_id  (pequeño, fijo)
      - file_id         (grande, puede caducar)
    El cliente local convertirá ese id en el token temporal.
    """
    rng = request.headers.get("range", "")
    headers = {"Accept-Ranges": "bytes"}
    status  = 206 if rng else 200

    async def gen():
        async with httpx.AsyncClient(timeout=None) as cli:
            # 1. pedimos al cliente local que abra el fichero en Telegram
            params = {"file_id": file_id, "range": rng}
            async with cli.stream("GET", f"{LOCAL_URL}/tg_open", params=params) as r:
                async for chunk in r.aiter_bytes(64*1024):
                    yield chunk

    return StreamingResponse(gen(), status_code=status, headers=headers)
