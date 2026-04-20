# BITS WILP · Cloud Computing (Sem 2) · Distributed Computing Assignment II

This repository contains the implementation for **Distributed Computing
Assignment II** — a 3-node distributed *chat room* in which two user nodes
share a chat file hosted on a third (file-server) node, and coordinate
write access to that file using the **Ricart–Agrawala Distributed Mutual
Exclusion** algorithm.

The project is implemented in **Python 3** using only the standard library
and is designed to run identically on macOS, Linux (including the OSHA
Cloud Lab Linux VM used for demonstration) and Windows.

## Repository layout

```
.
├── chatroom/                      # The actual implementation
│   ├── config.py                  # Ports, node IDs, usernames (shared config)
│   ├── logger.py                  # Structured logger (stdout + per-node file)
│   ├── dme.py                     # Pure Ricart-Agrawala DME middleware
│   ├── file_server.py             # Node 0 — shared chat file RPC server
│   ├── chat_app.py                # User CLI application (calls DME)
│   ├── run_node.py                # Launcher: python run_node.py <0|1|2>
│   ├── test_concurrent.py         # Optional concurrent DME stress test
│   └── README.md                  # Detailed usage & verification guide
├── .gitignore
└── README.md                      # (this file)
```

## Quick start

From the repository root:

```bash
cd chatroom

# Terminal 1 — file server (Node 0)
python3 run_node.py 0

# Terminal 2 — Alice (Node 1)
python3 run_node.py 1

# Terminal 3 — Bob (Node 2)
python3 run_node.py 2
```

Then on either user terminal:

```
Alice> view
Alice> post Welcome to the team project
Alice> quit
```

See [`chatroom/README.md`](chatroom/README.md) for full details, including
how each node’s `node_<id>.log` can be used to verify that the Ricart–Agrawala
algorithm is correctly serialising access to the critical section.

## Assignment requirements coverage

| Requirement                                                      | Where |
|------------------------------------------------------------------|-------|
| Shared chat file stored on a single server node                  | `chatroom/file_server.py` + `chat.txt` |
| `view` and `post` CLI commands on user nodes                     | `chatroom/chat_app.py` |
| `view` / `post` exposed as RPCs on the file server               | `handle_rpc` in `chatroom/file_server.py` |
| Many concurrent readers allowed                                  | `view` path does **not** take the DME lock |
| Single writer (mutual exclusion on `post`)                       | `chatroom/dme.py` (Ricart–Agrawala) |
| Each post records user-side time, node id, text                  | `cmd_post` in `chatroom/chat_app.py` |
| DME middleware and user app kept as separate modules             | `dme.py` vs `chat_app.py` |
| Logs prove DME is actually working                               | `node_<id>.log` written by `logger.py` |
| Non-centralized DME algorithm                                    | Ricart–Agrawala (peer-to-peer REQUEST/REPLY) |

## Platform notes

- **Local dev (macOS / Linux / Windows)** — all three node processes run on
  `127.0.0.1` and talk over loopback. This is the default configuration in
  `chatroom/config.py`.
- **OSHA Cloud Lab Linux VM** — clone this repo on the VM, open three
  shells (or three `tmux` panes), and run the three nodes as above. If you
  split the nodes across three VMs, edit `chatroom/config.py` so each
  entry’s `host` points to the correct private IP and open the TCP ports
  (9000 / 9001 / 9002 by default) on any intervening firewalls.
