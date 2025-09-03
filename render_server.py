from flask import Flask, request, Response, stream_with_context
import queue

app = Flask(__name__)
request_queue = queue.Queue()
response_buffers = {}

@app.route("/poll", methods=["GET", "POST"])
def poll():
    """Polling endpoint para el cliente local."""
    if request.method == "POST":
        # Cliente local envía chunks de la respuesta
        key = request.headers.get("X-Request-ID")
        if key and key in response_buffers:
            response_buffers[key].put(request.data)
        return "OK"
    else:
        # Devuelve path pendiente a la máquina local
        try:
            path = request_queue.get_nowait()
            return path
        except queue.Empty:
            return ""

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def handle_request(path):
    """Recibe request pública y agrega a la cola."""
    import uuid
    request_id = str(uuid.uuid4())
    request_queue.put(path)
    response_buffers[request_id] = queue.Queue()

    @stream_with_context
    def generate():
        buffer = response_buffers[request_id]
        while True:
            chunk = buffer.get()
            if chunk == b"__END__":
                break
            yield chunk
        del response_buffers[request_id]

    headers = {"X-Request-ID": request_id}
    return Response(generate(), headers=headers, mimetype="application/octet-stream")
    
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
