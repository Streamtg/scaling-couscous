#!/usr/bin/env python3
from flask import Flask, request, send_from_directory, abort, Response
import os

# ======================
# CONFIGURACIÓN
LOCAL_DIR = os.path.join(os.getcwd(), "public")  # Carpeta con tus archivos para servir
PORT = int(os.environ.get("PORT", 8080))       # Render define automáticamente PORT
# ======================

app = Flask(__name__, static_folder=LOCAL_DIR, static_url_path="")

# Ruta principal: sirve archivos estáticos
@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def serve_file(path):
    file_path = os.path.join(LOCAL_DIR, path)
    if os.path.isfile(file_path):
        return send_from_directory(LOCAL_DIR, path)
    else:
        return abort(404)

# Endpoint de prueba o proxy dinámico (opcional)
@app.route("/proxy/<path:url>", methods=["GET", "POST"])
def proxy(url):
    try:
        import requests
        target_url = f"http://127.0.0.1:8080/{url}"  # Redirige a localhost interno si es necesario
        if request.method == "GET":
            r = requests.get(target_url, params=request.args)
        elif request.method == "POST":
            r = requests.post(target_url, data=request.form)
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in r.headers.items() if name.lower() not in excluded_headers]
        return Response(r.content, r.status_code, headers)
    except Exception as e:
        return Response(f"Error proxying request: {e}", status=502)

if __name__ == "__main__":
    if not os.path.exists(LOCAL_DIR):
        os.makedirs(LOCAL_DIR)
        with open(os.path.join(LOCAL_DIR, "index.html"), "w") as f:
            f.write("<h1>Servidor Render Python funcionando!</h1>")
    print(f"[*] Servidor Flask público iniciado en el puerto {PORT}, sirviendo {LOCAL_DIR}")
    app.run(host="0.0.0.0", port=PORT)
