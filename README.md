# Distributed Chat Room — DC Assignment II

3-node distributed chat-room application written in **Python 3** (standard library only).  
Two user nodes share a chat file hosted on a dedicated file-server node. Write access to the shared file is serialised using the **Ricart–Agrawala Distributed Mutual Exclusion** algorithm.

---

## Node layout

| Node | Role        | Port | Description                              |
|------|-------------|------|------------------------------------------|
| 0    | File Server | 9000 | Hosts `chat.txt`; handles VIEW / POST RPCs |
| 1    | Alice       | 9001 | DME peer + CLI chat client               |
| 2    | Bob         | 9002 | DME peer + CLI chat client               |

The three nodes are independent OS processes communicating over TCP on `127.0.0.1`. To run across multiple machines, change each node's `host` in `chatroom/config.py` to the appropriate IP address and open the relevant ports.

---

## Project structure

```
chatroom/
├── config.py           # Ports, node IDs, usernames
├── logger.py           # Structured logger — stdout + node_<id>.log
├── dme.py              # Ricart-Agrawala DME middleware (no chat logic)
├── file_server.py      # Node 0: VIEW / POST RPC server
├── chat_app.py         # User CLI — calls dme.acquire() / dme.release()
├── run_node.py         # Launcher
└── test_concurrent.py  # Concurrent DME stress test
```

### Module separation (assignment requirement)

| Module           | Responsibility |
|------------------|----------------|
| `dme.py`         | Pure Ricart–Agrawala. Knows nothing about the chat application. Exposes `acquire()` and `release()`. |
| `chat_app.py`    | CLI chat client. Calls `dme.acquire()` / `dme.release()` as a black box around every `post`. |
| `file_server.py` | Shared resource server. Does **not** participate in DME. |
| `config.py`      | Shared configuration. |
| `logger.py`      | Per-node log files for DME verification. |

Enforced in code:
- `dme.py` imports nothing from `chat_app.py` or `file_server.py`.
- `chat_app.py` only calls `dme.acquire()` and `dme.release()`.
- `file_server.py` does not import `dme.py`.

---

## Requirements

- Python 3.8 or later
- No third-party packages
- macOS, Linux, Windows

---

## Running

Open three terminals and `cd` into the `chatroom/` directory in each.

**Terminal 1 — file server**
```bash
python3 run_node.py 0
```

**Terminal 2 — Alice**
```bash
python3 run_node.py 1
```

**Terminal 3 — Bob**
```bash
python3 run_node.py 2
```

### Available commands (on user nodes)

```
Alice> view                     # fetch and print all messages
Alice> post Hello team!         # acquire DME lock, append message, release
Alice> post "quoted message"    # quotes around the text are optional
Alice> quit                     # exit
```

---

## How DME correctness is verified

Each node writes structured log output to stdout and to its own log file:

```
node_0.log   — file-server RPC trace
node_1.log   — Alice: DME events + app actions
node_2.log   — Bob:   DME events + app actions
```

A correct run will show sequences like:

```
[ACQUIRE] Broadcasting REQUEST(ts=1) to peers [2]
[REQUEST <-] from Node-2  ts=1
[REQUEST] We have priority ((1, 1) <= (1, 2)) -> DEFERRED reply to Node-2
[REPLY <-] from Node-2  ts=3
[ACQUIRE] *** CS GRANTED -- entering critical section ***
[RELEASE] Exiting CS. Sending deferred REPLYs to: [2]
```

At most one node is ever in `CS GRANTED` state at a time.

### Automated contention test

With Node 0 running, run the following in a separate terminal from `chatroom/`:

```bash
python3 test_concurrent.py
```

This fires three concurrent `post` calls each from Alice and Bob simultaneously, then prints the final `chat.txt`. Check `node_1.log` and `node_2.log` to verify that the Lamport timestamp tie-breaking and deferred replies work correctly under contention.

---

## Sample `chat.txt`

```
21 Apr 09:01AM  Alice: Welcome to the team project
21 Apr 09:04AM  Bob: Thanks Alice - hope to work together
21 Apr 09:05AM  Alice: Bob, will send you the project outline by eod
```

---

## Ricart–Agrawala algorithm

Each user node maintains a Lamport logical clock and one of three states: `RELEASED`, `WANTED`, or `HELD`.

To enter the critical section a node increments its clock, broadcasts `REQUEST(timestamp, node_id)` to all peers, and blocks until it has received a `REPLY` from every peer.

On receiving a `REQUEST` from peer P:
- If the local node is `RELEASED` → reply immediately.
- If the local node is `HELD` → defer the reply until after release.
- If the local node is `WANTED` → compare `(timestamp, node_id)` tuples. The lower tuple wins. If the peer has the lower tuple, reply immediately. Otherwise defer.

On `release()`, the node sends deferred replies to all nodes it held back, allowing them to enter the critical section in turn. No central coordinator is involved.
