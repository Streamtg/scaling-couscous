from flask import Flask, request, Response, stream_with_context

app = Flask(__name__)
queue = []

@app.route("/poll", methods=["GET", "POST"])
def poll():
    if request.method == "POST":
        # Acumular chunks recibidos de la máquina local
        return "OK"
    else:
        # Devolver el siguiente path a la máquina local
        if queue:
            return queue.pop(0)
        return ""

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def handle_request(path):
    # Agregamos el path a la cola para que la máquina local lo procese
    queue.append(path)

    # Respuesta streaming simulada
    @stream_with_context
    def generate():
        # Render recibirá los datos enviados en chunks por la máquina local
        while True:
            yield b""  # Inicialmente vacío; los chunks reales llegan vía POST
    return Response(generate(), status=200, mimetype="application/octet-stream")

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
