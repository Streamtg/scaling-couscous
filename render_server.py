# tunnel_advanced.py
import asyncio
import aiohttp
import os
from aiohttp import ClientSession, ClientTimeout

SERVER_URL = "https://streammgram.onrender.com"
CHUNK_SIZE = 1024 * 64  # 64KB por chunk
MAX_RETRIES = 5
POLL_INTERVAL = 0.5  # segundos

async def poll_worker():
    """Consulta constante al servidor por paths a procesar"""
    async with ClientSession(timeout=ClientTimeout(total=None)) as session:
        while True:
            try:
                async with session.get(f"{SERVER_URL}/poll") as resp:
                    path = (await resp.text()).strip()
                    if path:
                        asyncio.create_task(stream_path(path, session))
            except Exception as e:
                print(f"[!] Error en polling: {e}")
            await asyncio.sleep(POLL_INTERVAL)

async def stream_path(path, session: ClientSession):
    """Envía un archivo local al servidor en chunks con reintentos automáticos"""
    file_path = path.lstrip("/")
    if not os.path.isfile(file_path):
        print(f"[!] Archivo no encontrado: {file_path}")
        return

    try:
        with open(file_path, "rb") as f:
            chunk_num = 0
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                for attempt in range(MAX_RETRIES):
                    try:
                        await session.post(f"{SERVER_URL}/send_chunk", data=chunk)
                        break
                    except Exception as e:
                        print(f"[!] Error enviando chunk {chunk_num}, intento {attempt+1}: {e}")
                        await asyncio.sleep(0.5)
                chunk_num += 1

        # Enviar señal de fin de archivo
        await session.post(f"{SERVER_URL}/send_chunk", data=b"")
        print(f"[+] Archivo {file_path} enviado correctamente")

    except Exception as e:
        print(f"[!] Error streaming {file_path}: {e}")

if __name__ == "__main__":
    asyncio.run(poll_worker())
