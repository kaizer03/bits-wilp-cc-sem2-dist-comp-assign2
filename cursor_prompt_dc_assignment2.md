# Cursor IDE Prompt — Distributed Chat Room (DC Assignment II)

## Context & Goal

Build a **3-node distributed chat room** on a **single Linux VM** using **Python 3**.  
The three nodes are **logical processes** on the same machine communicating via TCP sockets.  
The system must implement the **Ricart-Agrawala Distributed Mutual Exclusion (DME)** algorithm to control write access to a shared chat file hosted on one of the nodes.

---

## Project Directory Layout

Create the following files exactly:

```
chatroom/
├── file_server.py        # Node 0 — the file server (resource manager)
├── dme.py                # DME middleware — Ricart-Agrawala algorithm (pure, reusable module)
├── chat_app.py           # User application — CLI chat client using DME
├── run_node.py           # Entry point launcher (starts any of the 3 node roles)
├── config.py             # Shared configuration (ports, node IDs, usernames)
├── logger.py             # Structured DME + app logger
└── README.md             # How to run
```

---

## Node Roles & Ports

| Node ID | Role        | Port  | Description                              |
|---------|-------------|-------|------------------------------------------|
| 0       | File Server | 9000  | Hosts `chat.txt`, handles view/post RPCs |
| 1       | User Alice  | 9001  | DME peer + CLI chat client               |
| 2       | User Bob    | 9002  | DME peer + CLI chat client               |

---

## `config.py`

```python
# config.py — shared configuration for all nodes

NODE_COUNT = 3

# Node 0 = file server; nodes 1 and 2 = user nodes
NODES = {
    0: {"host": "127.0.0.1", "port": 9000, "username": "Server"},
    1: {"host": "127.0.0.1", "port": 9001, "username": "Alice"},
    2: {"host": "127.0.0.1", "port": 9002, "username": "Bob"},
}

# User nodes that participate in DME
USER_NODES = [1, 2]

FILE_SERVER_NODE = 0
CHAT_FILE = "chat.txt"

# DME message types
MSG_REQUEST = "REQUEST"
MSG_REPLY   = "REPLY"
MSG_RELEASE = "RELEASE"   # optional, for completeness in logs

# RPC command types (user node → file server)
RPC_VIEW = "VIEW"
RPC_POST = "POST"
```

---

## `logger.py`

```python
# logger.py — structured logger used by all modules

import logging
import sys

def get_logger(name: str, node_id: int) -> logging.Logger:
    logger = logging.getLogger(f"{name}[Node-{node_id}]")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter(
            fmt="%(asctime)s  %(name)-22s  %(levelname)-7s  %(message)s",
            datefmt="%H:%M:%S.%f"
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)

        # Also write to a per-node log file for verification
        fh = logging.FileHandler(f"node_{node_id}.log", mode="a")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.setLevel(logging.DEBUG)
    return logger
```

---

## `dme.py` — Ricart-Agrawala DME Middleware

This is the **pure DME module**. It has zero knowledge of the chat application.  
It exposes two public methods: `acquire()` and `release()`.

The Ricart-Agrawala algorithm:
- Every node maintains a **Lamport logical clock**.
- To enter the **Critical Section (CS)**: broadcast `REQUEST(clock, node_id)` to all peers, then **block** until `N-1` REPLY messages are received (one from each peer).
- On receiving a `REQUEST` from peer P:
  - If the local node is **not** in CS and **not** waiting for CS → immediately send `REPLY`.
  - If the local node is **in CS** → defer the reply (add P to a deferred queue).
  - If the local node is **waiting for CS** (has sent its own REQUEST):
    - Compare timestamps. If peer's (timestamp, id) < own (timestamp, id) → send `REPLY` immediately (peer has priority).
    - Else → defer the reply.
- On `release()`: send `REPLY` to all deferred nodes and reset state.

```python
# dme.py — Ricart-Agrawala Distributed Mutual Exclusion
# This module is INDEPENDENT of the chat application.

import socket
import threading
import json
import time
from config import NODES, USER_NODES, MSG_REQUEST, MSG_REPLY, MSG_RELEASE
from logger import get_logger

class RicartAgrawala:
    """
    Ricart-Agrawala DME algorithm.

    Public API:
        acquire()  — blocks until the CS is granted
        release()  — exits CS, notifies deferred nodes
    """

    STATE_RELEASED = "RELEASED"   # not interested in CS
    STATE_WANTED   = "WANTED"     # waiting for all REPLYs
    STATE_HELD     = "HELD"       # inside CS

    def __init__(self, node_id: int):
        self.node_id   = node_id
        self.log       = get_logger("DME", node_id)

        self.clock     = 0           # Lamport logical clock
        self.state     = self.STATE_RELEASED
        self.request_ts = None       # timestamp of our own last REQUEST

        self.reply_count   = 0       # replies received for current request
        self.needed_replies = len(USER_NODES) - 1   # N-1 peers
        self.deferred      = []      # list of node_ids whose REPLY we deferred

        self._lock         = threading.Lock()
        self._cs_event     = threading.Event()   # set when all replies received

        # Start the DME listener thread
        self._server_thread = threading.Thread(
            target=self._listen, daemon=True, name=f"DME-listener-{node_id}"
        )
        self._server_thread.start()
        self.log.info(
            f"DME listener started on port {NODES[node_id]['port']}"
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def acquire(self):
        """Block until this node holds the CS."""
        with self._lock:
            self._increment_clock()
            self.request_ts = self.clock
            self.state      = self.STATE_WANTED
            self.reply_count = 0
            self._cs_event.clear()
            req_clock = self.request_ts

        self.log.info(
            f"[ACQUIRE] Broadcasting REQUEST(ts={req_clock}) to peers {[n for n in USER_NODES if n != self.node_id]}"
        )

        self._broadcast({
            "type":    MSG_REQUEST,
            "clock":   req_clock,
            "node_id": self.node_id,
        })

        # Block until we have received N-1 REPLYs
        self.log.info("[ACQUIRE] Waiting for REPLY from all peers...")
        self._cs_event.wait()

        with self._lock:
            self.state = self.STATE_HELD

        self.log.info("[ACQUIRE] *** CS GRANTED — entering critical section ***")

    def release(self):
        """Release the CS and flush deferred REPLYs."""
        with self._lock:
            self.state  = self.STATE_RELEASED
            deferred_copy = list(self.deferred)
            self.deferred = []

        self.log.info(
            f"[RELEASE] Exiting CS. Sending deferred REPLYs to: {deferred_copy}"
        )

        for peer_id in deferred_copy:
            self._send_to(peer_id, {
                "type":    MSG_REPLY,
                "clock":   self._get_clock(),
                "node_id": self.node_id,
            })
            self.log.debug(f"[RELEASE] Sent REPLY → Node-{peer_id}")

    # ------------------------------------------------------------------ #
    #  Internal — message handling                                         #
    # ------------------------------------------------------------------ #

    def _listen(self):
        """Listen for incoming REQUEST / REPLY messages from DME peers."""
        host = NODES[self.node_id]["host"]
        port = NODES[self.node_id]["port"]
        srv  = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(10)
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(
                target=self._handle_conn, args=(conn,), daemon=True
            )
            t.start()

    def _handle_conn(self, conn):
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            if data:
                msg = json.loads(data.decode())
                self._process_message(msg)
        except Exception as e:
            self.log.error(f"DME handle_conn error: {e}")
        finally:
            conn.close()

    def _process_message(self, msg: dict):
        mtype    = msg["type"]
        peer_id  = msg["node_id"]
        peer_ts  = msg["clock"]

        with self._lock:
            # Update Lamport clock on receive
            self.clock = max(self.clock, peer_ts) + 1

        if mtype == MSG_REQUEST:
            self._on_request(peer_id, peer_ts)
        elif mtype == MSG_REPLY:
            self._on_reply(peer_id, peer_ts)

    def _on_request(self, peer_id: int, peer_ts: int):
        self.log.info(
            f"[REQUEST ←] from Node-{peer_id}  ts={peer_ts}"
        )
        send_reply_now = False

        with self._lock:
            if self.state == self.STATE_HELD:
                # We are in CS — must defer
                self.deferred.append(peer_id)
                self.log.debug(
                    f"[REQUEST] In CS → DEFERRED reply to Node-{peer_id}"
                )
            elif self.state == self.STATE_WANTED:
                # We also want CS — compare timestamps (lower wins; break ties by node_id)
                our_ts   = (self.request_ts, self.node_id)
                their_ts = (peer_ts, peer_id)
                if their_ts < our_ts:
                    # Peer has priority → reply immediately
                    send_reply_now = True
                    self.log.debug(
                        f"[REQUEST] Peer Node-{peer_id} has priority ({their_ts} < {our_ts}) → immediate REPLY"
                    )
                else:
                    # We have priority → defer
                    self.deferred.append(peer_id)
                    self.log.debug(
                        f"[REQUEST] We have priority ({our_ts} <= {their_ts}) → DEFERRED reply to Node-{peer_id}"
                    )
            else:
                # STATE_RELEASED — reply immediately
                send_reply_now = True
                self.log.debug(
                    f"[REQUEST] Not interested in CS → immediate REPLY to Node-{peer_id}"
                )

        if send_reply_now:
            self._send_to(peer_id, {
                "type":    MSG_REPLY,
                "clock":   self._get_clock(),
                "node_id": self.node_id,
            })
            self.log.info(f"[REPLY →] sent to Node-{peer_id}")

    def _on_reply(self, peer_id: int, peer_ts: int):
        self.log.info(f"[REPLY ←] from Node-{peer_id}  ts={peer_ts}")
        with self._lock:
            self.reply_count += 1
            self.log.debug(
                f"[REPLY] reply_count={self.reply_count}/{self.needed_replies}"
            )
            if self.reply_count >= self.needed_replies:
                self._cs_event.set()

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _increment_clock(self):
        self.clock += 1
        return self.clock

    def _get_clock(self):
        with self._lock:
            self.clock += 1
            return self.clock

    def _broadcast(self, msg: dict):
        for peer_id in USER_NODES:
            if peer_id != self.node_id:
                self._send_to(peer_id, msg)

    def _send_to(self, peer_id: int, msg: dict):
        host = NODES[peer_id]["host"]
        port = NODES[peer_id]["port"]
        data = json.dumps(msg).encode()
        retry = 5
        for attempt in range(retry):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((host, port))
                s.sendall(data)
                s.close()
                return
            except Exception as e:
                self.log.warning(
                    f"_send_to Node-{peer_id} attempt {attempt+1} failed: {e}"
                )
                time.sleep(0.3 * (attempt + 1))
        self.log.error(f"Failed to send to Node-{peer_id} after {retry} attempts")
```

---

## `file_server.py` — Node 0: Shared File Resource Server

This is a **simple TCP RPC server**. It only handles `VIEW` and `POST` commands.  
It does **not** participate in DME — it just safely reads/appends to `chat.txt`.

```python
# file_server.py — Node 0: File server (resource manager)
# Exposes VIEW and POST RPCs over TCP.
# Not part of the DME protocol — it is the guarded resource.

import socket
import threading
import json
import os
from datetime import datetime
from config import NODES, FILE_SERVER_NODE, CHAT_FILE, RPC_VIEW, RPC_POST
from logger import get_logger

log = get_logger("FileServer", FILE_SERVER_NODE)

# Thread lock for file I/O (protects server-side concurrent access, belt-and-suspenders)
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
            log.info(f"[RPC] POST from Node-{node_id} ({username}): {text!r}")

        else:
            response = {"status": "error", "msg": f"Unknown command: {cmd}"}
            log.warning(f"[RPC] Unknown command from {addr}: {cmd}")

        conn.sendall(json.dumps(response).encode())

    except Exception as e:
        log.error(f"[RPC] Error handling request from {addr}: {e}")
        try:
            conn.sendall(json.dumps({"status": "error", "msg": str(e)}).encode())
        except:
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
    log.info(f"File server listening on {host}:{port}  (chat file: {CHAT_FILE})")

    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_rpc, args=(conn, addr), daemon=True)
        t.start()


if __name__ == "__main__":
    run_file_server()
```

---

## `chat_app.py` — User Node: CLI Chat Application

This module **calls** the DME middleware and **calls** the file server RPC.  
It is **completely separate** from `dme.py` — it only calls `dme.acquire()` and `dme.release()`.

```python
# chat_app.py — User node CLI chat application
# Depends on: dme.py (DME middleware), config.py
# Does NOT implement any DME logic itself.

import socket
import json
import sys
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

            # Read response
            data = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
            s.close()
            return json.loads(data.decode())
        except Exception as e:
            log.warning(f"RPC attempt {attempt+1} failed: {e}")
            time.sleep(0.5)
    raise ConnectionError("File server unreachable after 5 attempts")


def cmd_view(node_id: int, username: str, log):
    """
    view — fetch and display the current chat file contents.
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


def cmd_post(text: str, node_id: int, username: str, dme: RicartAgrawala, log):
    """
    post <text> — acquire DME lock, post to file server, release lock.
    Only one user node may be in the critical section at a time.
    """
    if not text.strip():
        print("[ERROR] Post text cannot be empty.")
        return

    log.info(f"[APP] post command — acquiring DME lock for user {username}")

    # ---- ENTER CRITICAL SECTION via DME ----
    dme.acquire()

    try:
        timestamp = datetime.now().strftime("%d %b %I:%M%p")
        log.info(f"[APP] In CS — posting to file server: {text!r}")

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
        log.info(f"[APP] DME lock released after post")


def run_chat_app(node_id: int):
    username = NODES[node_id]["username"]
    log = get_logger("ChatApp", node_id)

    log.info(f"Starting chat app as Node-{node_id} ({username})")
    print(f"\n=== Distributed Chat Room ===")
    print(f"Logged in as: {username}  (Node {node_id})")
    print(f"Commands:  view  |  post <your message>  |  quit\n")

    # Initialize DME middleware
    log.info(f"Initializing Ricart-Agrawala DME middleware for Node-{node_id}")
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

        if cmd == "quit" or cmd == "exit":
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
            print(f"Unknown command: {cmd!r}. Use: view | post <text> | quit")
```

---

## `run_node.py` — Entry Point

```python
# run_node.py — Launches any of the three node roles.
# Usage:
#   python run_node.py 0          → start file server (Node 0)
#   python run_node.py 1          → start user Alice  (Node 1)
#   python run_node.py 2          → start user Bob    (Node 2)

import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_node.py <node_id>")
        print("  node_id 0 → File Server")
        print("  node_id 1 → User Alice")
        print("  node_id 2 → User Bob")
        sys.exit(1)

    try:
        node_id = int(sys.argv[1])
    except ValueError:
        print("node_id must be an integer (0, 1, or 2)")
        sys.exit(1)

    if node_id == 0:
        from file_server import run_file_server
        run_file_server()

    elif node_id in (1, 2):
        from chat_app import run_chat_app
        run_chat_app(node_id)

    else:
        print(f"Invalid node_id: {node_id}. Must be 0, 1, or 2.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## `README.md`

````markdown
# Distributed Chat Room — DC Assignment II

## Overview

- 3-node distributed system on a single Linux VM using Python 3.
- **Node 0**: File server (shared resource). Hosts `chat.txt`.
- **Node 1**: User "Alice" — DME peer + CLI chat client.
- **Node 2**: User "Bob" — DME peer + CLI chat client.
- **DME Algorithm**: Ricart-Agrawala (non-centralized, message-passing based).
- **No external dependencies** — uses Python standard library only.

## Module Responsibilities (Assignment Requirement)

| Module | Role |
|---|---|
| `dme.py` | **DME Middleware** — Pure Ricart-Agrawala implementation. No chat logic. |
| `chat_app.py` | **User Application** — CLI chat client. Calls `dme.acquire()`/`release()`. |
| `file_server.py` | File resource server. VIEW and POST RPCs. No DME participation. |
| `config.py` | Shared configuration (ports, node IDs, usernames). |
| `logger.py` | Structured logger — writes to stdout and `node_N.log` files. |
| `run_node.py` | Entry point launcher. |

## How to Run (3 separate terminals on the same machine)

### Terminal 1 — Start File Server (Node 0)
```bash
cd chatroom/
python run_node.py 0
```

### Terminal 2 — Start Alice's node (Node 1)
```bash
cd chatroom/
python run_node.py 1
```

### Terminal 3 — Start Bob's node (Node 2)
```bash
cd chatroom/
python run_node.py 2
```

## CLI Commands (Terminals 2 and 3)

```
Alice> view                          # Pull and display all chat messages
Alice> post "Hello team!"            # Acquire DME lock, append message, release lock
Alice> post Hello without quotes     # Quotes are optional
Alice> quit                          # Exit
```

## How DME is Verified

1. Each node writes its own `node_N.log` file.
2. Log lines show: REQUEST broadcast, REPLY sent/deferred, CS GRANTED, CS RELEASED.
3. To test contention: rapidly post from both Alice and Bob simultaneously.
4. Check logs to confirm:
   - Both nodes broadcast REQUEST with timestamps.
   - The node with the lower (timestamp, node_id) pair wins.
   - The losing node's REPLY is deferred until the winner releases.
   - No two nodes are ever in CS simultaneously.

## Sample Log Output (Node 1 — Alice)

```
09:01:05  DME[Node-1]         INFO     DME listener started on port 9001
09:01:06  ChatApp[Node-1]     INFO     DME ready. Waiting for user commands.
09:01:10  ChatApp[Node-1]     INFO     [APP] post command — acquiring DME lock for user Alice
09:01:10  DME[Node-1]         INFO     [ACQUIRE] Broadcasting REQUEST(ts=3) to peers [2]
09:01:10  DME[Node-1]         INFO     [ACQUIRE] Waiting for REPLY from all peers...
09:01:10  DME[Node-1]         INFO     [REPLY ←] from Node-2  ts=4
09:01:10  DME[Node-1]         INFO     [ACQUIRE] *** CS GRANTED — entering critical section ***
09:01:10  ChatApp[Node-1]     INFO     [APP] In CS — posting to file server
09:01:10  DME[Node-1]         INFO     [RELEASE] Exiting CS. Sending deferred REPLYs to: []
09:01:10  ChatApp[Node-1]     INFO     [APP] DME lock released after post
```

## Sample Shared File (`chat.txt`)
```
12 Oct 09:01AM  Alice: Welcome to the team project
12 Oct 09:04AM  Bob: Thanks Alice - hope to work together
12 Oct 09:05AM  Alice: Bob, will send you the project outline by eod
```
````

---

## Implementation Instructions for Cursor

> **Follow these instructions exactly. Do not deviate from the architecture.**

1. **Create the directory `chatroom/`** and place all 7 files inside it exactly as specified above.

2. **Do not merge `dme.py` and `chat_app.py`** — the assignment explicitly requires them to be separate modules. The chat app calls `dme.acquire()` and `dme.release()` as black-box API calls.

3. **Node 0 (file server) does NOT participate in DME** — it is the resource being protected. Only Nodes 1 and 2 run the DME middleware.

4. **The DME listener (TCP server in `dme.py`)** must be started in a **background daemon thread** so it does not block the main CLI loop.

5. **Use only Python standard library** — `socket`, `threading`, `json`, `logging`, `datetime`. No `pip install` required.

6. **Logging**: Every DME message (REQUEST sent, REPLY sent, REPLY received, deferred, CS granted, CS released) must be logged with timestamp, node ID, and logical clock value. This is for assignment verification.

7. **Lamport clock rules in Ricart-Agrawala**:
   - Increment clock on every internal event and before sending any message.
   - On receive: `clock = max(local_clock, received_clock) + 1`.
   - Tie-breaking: when two REQUESTs have the same timestamp, the node with the **lower node_id** wins.

8. **`view` is read-only and requires NO DME locking** — multiple nodes may call view simultaneously. Only `post` requires the DME lock.

9. **Error handling**: All socket operations must use `try/except` with retry logic. If the file server or a DME peer is not yet reachable, retry up to 5 times with increasing delay.

10. **Do not use any centralized coordinator node for DME** — it must be the pure peer-to-peer Ricart-Agrawala algorithm.

11. After creating all files, **verify correctness** by:
    - Checking that `dme.py` imports nothing from `chat_app.py`.
    - Checking that `chat_app.py` only calls `dme.acquire()` and `dme.release()`.
    - Checking that `file_server.py` imports nothing from `dme.py`.

12. **The `post` command records the time on the user node** (not server time) using `datetime.now()` at the moment the user issues the command (before acquiring the DME lock, timestamp taken), per assignment requirement 7.

---

## Quick Correctness Test Script (Optional — add as `test_concurrent.py`)

```python
# test_concurrent.py — Simulate concurrent posts from Alice and Bob
# Run this INSTEAD of interactive CLI to stress-test the DME algorithm.
# Requires Node 0 (file server) to already be running.
# Run: python test_concurrent.py

import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from config import USER_NODES
from dme import RicartAgrawala
from chat_app import cmd_post, cmd_view
from logger import get_logger

POSTS_PER_NODE = 3

def node_worker(node_id):
    from config import NODES
    username = NODES[node_id]["username"]
    log = get_logger("TestWorker", node_id)
    dme = RicartAgrawala(node_id)
    time.sleep(1)  # let all DME listeners start

    for i in range(POSTS_PER_NODE):
        msg = f"Test message {i+1} from {username}"
        print(f"[Test] Node-{node_id} attempting: {msg}")
        cmd_post(msg, node_id, username, dme, log)
        time.sleep(0.2)

if __name__ == "__main__":
    print("Starting concurrent DME stress test...")
    print("Make sure Node 0 (file server) is running first!\n")

    threads = [
        threading.Thread(target=node_worker, args=(nid,), name=f"Node-{nid}")
        for nid in USER_NODES
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("\n=== Final chat file contents ===")
    from logger import get_logger
    log = get_logger("Test", 99)
    from chat_app import cmd_view
    cmd_view(99, "Tester", log)
    print("\nCheck node_1.log and node_2.log to verify DME correctness.")
```

---

## Summary of What to Implement

| File | Lines (approx) | Status |
|---|---|---|
| `config.py` | ~30 | Fully specified above — copy exactly |
| `logger.py` | ~20 | Fully specified above — copy exactly |
| `dme.py` | ~160 | Fully specified above — copy exactly |
| `file_server.py` | ~80 | Fully specified above — copy exactly |
| `chat_app.py` | ~100 | Fully specified above — copy exactly |
| `run_node.py` | ~30 | Fully specified above — copy exactly |
| `README.md` | ~70 | Fully specified above — copy exactly |
| `test_concurrent.py` | ~45 | Optional but recommended |

**Copy all code blocks above verbatim into their respective files. If needed, do expand but do not blow out of context. Respect the guidelines of the actual assignment content mentioned in assignment_doc.md. Then verify, run, and test. After it is done, make sure to add a proper readme file for the project and a gitignore if necessary. A blank public repo is created with remote url https://github.com/kaizer03/bits-wilp-cc-sem2-dist-comp-assign2.git and nothing has been pushed into yet, so no 'main' branch yet. Once done, add all files to the repo with appropriate commit. DO NOT mention Cursor anywhere. Once tested locally on my macbook pro, will move this to the linux VM OSHA Lab for execution and demonstration. It should be running on all platforms.**
