# chat_app.py -- User node CLI chat application
# Depends on: dme.py (DME middleware), config.py
# Does NOT implement any DME logic itself -- only calls
# dme.acquire() / dme.release() as black-box API.

import socket
import json
import time
from datetime import datetime

from config import NODES, FILE_SERVER_NODE, RPC_VIEW, RPC_POST
from dme import RicartAgrawala
from logger import get_logger


def _rpc_call(cmd: str, payload: dict, log) -> dict:
    """Send an RPC call to the file server (Node 0)."""
    host = NODES[FILE_SERVER_NODE]["host"]
    port = NODES[FILE_SERVER_NODE]["port"]
    payload["cmd"] = cmd

    for attempt in range(5):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((host, port))
            s.sendall(json.dumps(payload).encode())
            s.shutdown(socket.SHUT_WR)

            data = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
            s.close()
            return json.loads(data.decode())
        except Exception as e:
            log.warning(f"RPC attempt {attempt + 1} failed: {e}")
            time.sleep(0.5 * (attempt + 1))
    raise ConnectionError("File server unreachable after 5 attempts")


def cmd_view(node_id: int, username: str, log):
    """
    view -- fetch and display the current chat file contents.
    Multiple users may call view simultaneously (no DME needed for reads).
    """
    log.info(f"[APP] view command called by {username}")
    try:
        resp = _rpc_call(RPC_VIEW, {"node_id": node_id}, log)
        if resp.get("status") == "ok":
            content = resp.get("content", "").strip()
            if content:
                print("\n" + content + "\n")
            else:
                print("\n[Chat room is empty. Be the first to post!]\n")
        else:
            print(f"[ERROR] View failed: {resp.get('msg')}")
    except Exception as e:
        print(f"[ERROR] Could not reach file server: {e}")


def cmd_post(text: str, node_id: int, username: str,
             dme: RicartAgrawala, log):
    """
    post <text> -- acquire DME lock, post to file server, release lock.
    Only one user node may be in the critical section at a time.
    """
    if not text or not text.strip():
        print("[ERROR] Post text cannot be empty.")
        return

    # Assignment requirement #7: record the time the post was called on the
    # user node (not server time). Captured BEFORE acquiring the lock.
    timestamp = datetime.now().strftime("%d %b %I:%M%p")

    log.info(
        f"[APP] post command -- acquiring DME lock for user {username} "
        f"(user-time={timestamp})"
    )

    # ---- ENTER CRITICAL SECTION via DME ----
    dme.acquire()

    try:
        log.info(f"[APP] In CS -- posting to file server: {text!r}")

        resp = _rpc_call(RPC_POST, {
            "node_id":   node_id,
            "username":  username,
            "timestamp": timestamp,
            "text":      text.strip(),
        }, log)

        if resp.get("status") == "ok":
            print(f"[Posted] {timestamp}  {username}: {text.strip()}")
        else:
            print(f"[ERROR] Post failed: {resp.get('msg')}")

    except Exception as e:
        print(f"[ERROR] Post failed: {e}")
        log.error(f"[APP] Post error in CS: {e}")

    finally:
        # ---- EXIT CRITICAL SECTION ----
        dme.release()
        log.info("[APP] DME lock released after post")


def run_chat_app(node_id: int):
    username = NODES[node_id]["username"]
    log = get_logger("ChatApp", node_id)

    log.info(f"Starting chat app as Node-{node_id} ({username})")
    print("\n=== Distributed Chat Room ===")
    print(f"Logged in as: {username}  (Node {node_id})")
    print("Commands:  view  |  post <your message>  |  quit\n")

    log.info(
        f"Initializing Ricart-Agrawala DME middleware for Node-{node_id}"
    )
    dme = RicartAgrawala(node_id)

    # Give other nodes a moment to start their DME listeners
    time.sleep(1)
    log.info("DME ready. Waiting for user commands.")

    while True:
        try:
            raw = input(f"{username}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Exiting chat room]")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd   = parts[0].lower()

        if cmd in ("quit", "exit"):
            print("[Exiting chat room]")
            break

        elif cmd == "view":
            cmd_view(node_id, username, log)

        elif cmd == "post":
            if len(parts) < 2:
                print("Usage: post <your message>")
            else:
                text = parts[1]
                # Strip surrounding quotes if present
                if (text.startswith('"') and text.endswith('"')) or \
                   (text.startswith("'") and text.endswith("'")):
                    text = text[1:-1]
                cmd_post(text, node_id, username, dme, log)

        else:
            print(
                f"Unknown command: {cmd!r}. Use: view | post <text> | quit"
            )
