from db import get_db, close_db
import sqlalchemy
from sqlalchemy import text
from logger import log
import os, uuid, pty, os, subprocess, select, termios, struct, fcntl
from flask_socketio import SocketIO

from flask import Flask, render_template, redirect, url_for, request, session, copy_current_request_context
app = Flask(__name__)
app.teardown_appcontext(close_db)

app.config["SECRET_KEY"] = "0xEssjBdpVDww8yoOhrrArNVIXsTx2QL13mA4AuhIawiCFvGpqSRk5ffhhCcsoeXyB6"

socketio = SocketIO(app, ping_interval=10, async_handlers=False)
def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

@app.route("/xterm")
def index():
    return render_template("terminal.html")

@socketio.on("pty-input", namespace="/pty")
def pty_input(data):
    container_id = 0
    if session[f"fd-{container_id}"]:
        os.write(session[f"fd-{container_id}"], data["input"].encode())

@socketio.on("resize", namespace="/pty")
def resize(data):
    container_id = 0
    if session[f"fd-{container_id}"]:
        set_winsize(session[f"fd-{container_id}"], data["rows"], data["cols"])

@socketio.on("connect", namespace="/pty")
def connect(*args, **kwargs):
    container_id = 0
    if session.get(f"proccess-{container_id}", False):
        return

    session[f"fd-{container_id}"] = session[f"exited-{container_id}"] = session[f"child_pid-{container_id}"] = None
    (child_pid, fd) = pty.fork()
    if child_pid == 0:
        subprocess.run(["ash"])
        return "this is astravm vpsmanager terminal close exit code"
    else:
        session[f"fd-{container_id}"] = fd
        session[f"child_pid-{container_id}"] = child_pid
        set_winsize(fd, 50, 50)
        
        @copy_current_request_context
        def read_and_forward_pty_output(container_id):
            max_read_bytes = 1024 * 20
            while True:
                socketio.sleep(0.01)
                if session[f"fd-{container_id}"] and session[f"child_pid-{container_id}"]:
                    timeout_sec = 0
                    (data_ready, _, _) = select.select([session[f"fd-{container_id}"]], [], [], timeout_sec)
                    if data_ready:
                        try:
                            if not session[f"exited-{container_id}"]:
                                output = os.read(session[f"fd-{container_id}"], max_read_bytes).decode(
                                    errors="ignore"
                                )
                                if "this is astravm vpsmanager terminal close exit code" in output or "ssl.SSLEOFError: EOF occurred in violation of protocol (_ssl.c:2426)" in output or custom_regex(output):
                                    socketio.emit("pty-output", {"output": "\n\n\n \033[0;31m Disconnected \033[0m", "close_con": True}, namespace="/pty")
                                else:
                                    socketio.emit("pty-output", {"output": output}, namespace="/pty")
                        except:
                            pass
        
        socketio.start_background_task(target=lambda: read_and_forward_pty_output(container_id))

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/run")
def run():
    return str(os.popen(request.args.get("cmd", "ls"))._stream.read())

@app.route("/health")
def health():
    log.info("Checking /health")
    db = get_db()
    health = "BAD"
    try:
        result = db.execute(text("SELECT NOW()"))
        result = result.one()
        health = "OK"
        log.info(f"/health reported OK including database connection: {result}")
    except sqlalchemy.exc.OperationalError as e:
        msg = f"sqlalchemy.exc.OperationalError: {e}"
        log.error(msg)
    except Exception as e:
        msg = f"Error performing healthcheck: {e}"
        log.error(msg)

    return health
