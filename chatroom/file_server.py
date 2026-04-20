# file_server.py -- Node 0: File server (resource manager)
# Exposes VIEW and POST RPCs over TCP.
# Not part of the DME protocol -- it is the guarded resource.

import socket
import threading
import json
import os

from config import NODES, FILE_SERVER_NODE, CHAT_FILE, RPC_VIEW, RPC_POST
from logger import get_logger


log = get_logger("FileServer", FILE_SERVER_NODE)

# Thread lock for file I/O (protects server-side concurrent access,
# belt-and-suspenders in addition to the client-side DME)
_file_lock = threading.Lock()


def _ensure_file():
    if not os.path.exists(CHAT_FILE):
        with open(CHAT_FILE, "w") as f:
            f.write("")
        log.info(f"Created empty chat file: {CHAT_FILE}")


def handle_rpc(conn, addr):
    try:
        data = b""
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
        if not data:
            return

        req = json.loads(data.decode())
        cmd = req.get("cmd")

        if cmd == RPC_VIEW:
            with _file_lock:
                with open(CHAT_FILE, "r") as f:
                    content = f.read()
            response = {"status": "ok", "content": content}
            log.info(f"[RPC] VIEW requested by Node-{req.get('node_id','?')}")

        elif cmd == RPC_POST:
            text      = req.get("text", "")
            node_id   = req.get("node_id", "?")
            timestamp = req.get("timestamp", "")
            username  = req.get("username", f"Node-{node_id}")
            line      = f"{timestamp}  {username}: {text}\n"

            with _file_lock:
                with open(CHAT_FILE, "a") as f:
                    f.write(line)
            response = {"status": "ok"}
            log.info(
                f"[RPC] POST from Node-{node_id} ({username}): {text!r}"
            )

        else:
            response = {"status": "error", "msg": f"Unknown command: {cmd}"}
            log.warning(f"[RPC] Unknown command from {addr}: {cmd}")

        conn.sendall(json.dumps(response).encode())

    except Exception as e:
        log.error(f"[RPC] Error handling request from {addr}: {e}")
        try:
            conn.sendall(
                json.dumps({"status": "error", "msg": str(e)}).encode()
            )
        except Exception:
            pass
    finally:
        conn.close()


def run_file_server():
    _ensure_file()
    host = NODES[FILE_SERVER_NODE]["host"]
    port = NODES[FILE_SERVER_NODE]["port"]

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(20)
    log.info(
        f"File server listening on {host}:{port}  (chat file: {CHAT_FILE})"
    )

    while True:
        conn, addr = srv.accept()
        t = threading.Thread(
            target=handle_rpc, args=(conn, addr), daemon=True
        )
        t.start()


if __name__ == "__main__":
    run_file_server()
