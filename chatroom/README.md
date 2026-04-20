# Distributed Chat Room — DC Assignment II

A 3-node distributed chat-room application built in **Python 3** using only
the standard library. Two user nodes collaborate over a shared chat file
hosted on a third (file-server) node, and coordinate write access with the
**Ricart–Agrawala Distributed Mutual Exclusion (DME)** algorithm.

---

## Overview

| Node | Role         | Port  | Description                                  |
|------|--------------|-------|----------------------------------------------|
| 0    | File Server  | 9000  | Hosts `chat.txt`; handles `VIEW` / `POST` RPCs |
| 1    | User *Alice* | 9001  | DME peer + CLI chat client                   |
| 2    | User *Bob*   | 9002  | DME peer + CLI chat client                   |

The three nodes are *logical processes*; they run as three OS processes on a
single machine and communicate over TCP. They bind to `127.0.0.1` by default,
but any reachable host/port may be configured in `config.py` so the same code
runs unchanged on a Linux VM (e.g. OSHA Lab) or across three VMs.

## Module Responsibilities (per assignment requirement #1)

| Module            | Role |
|-------------------|------|
| `dme.py`          | **DME middleware** — pure Ricart–Agrawala. No chat logic, no RPC logic. Exposes `acquire()` / `release()`. |
| `chat_app.py`     | **User application** — CLI chat client. Calls `dme.acquire()` / `dme.release()` around each `post`. |
| `file_server.py`  | File resource server. Serves `VIEW` and `POST` RPCs. Does **not** participate in DME. |
| `config.py`       | Shared configuration — ports, node IDs, usernames. |
| `logger.py`       | Structured logger — writes to stdout and `node_<id>.log`. |
| `run_node.py`     | Entry-point launcher. |
| `test_concurrent.py` | Optional concurrent stress test for DME correctness. |

The separation above is enforced in code:

- `dme.py` does **not** import from `chat_app.py` or `file_server.py`.
- `chat_app.py` only touches DME through the two public calls.
- `file_server.py` does **not** import `dme.py`.

## Requirements

- Python **3.8+** (tested on 3.8 / 3.10 / 3.12)
- No third-party packages — standard library only.
- macOS, Linux, or Windows (uses only cross-platform APIs).

## How to Run (single machine, 3 terminals)

From the `chatroom/` directory.

### Terminal 1 — File server (Node 0)
```bash
python3 run_node.py 0
```

### Terminal 2 — User Alice (Node 1)
```bash
python3 run_node.py 1
```

### Terminal 3 — User Bob (Node 2)
```bash
python3 run_node.py 2
```

### CLI commands (on user nodes)

```
Alice> view                          # Pull and display all chat messages
Alice> post Hello team!              # Acquire DME, append, release
Alice> post "Hello with quotes"      # Quotes around the message are optional
Alice> quit                          # Exit
```

## Running on a Linux VM (e.g. the OSHA Cloud Lab)

1. `scp` or `git clone` the project onto the VM.
2. Ensure Python 3 is available: `python3 --version`.
3. Open three shells (three `tmux` panes / three `ssh` sessions also work).
4. Run `python3 run_node.py 0`, `1`, and `2` as above.

Using `127.0.0.1` keeps the demo self-contained on one VM. To run across
three VMs instead, edit `config.py` so every node’s `host` points to the
correct private IP and open the corresponding TCP ports in the firewall.

## How DME correctness is verified

Every DME event is logged with a timestamp, the node ID, and the relevant
Lamport clock values. Each node writes its own file:

```
node_0.log   # file-server RPC trace
node_1.log   # Alice: DME + app events
node_2.log   # Bob:   DME + app events
```

A successful run should show:

- `[ACQUIRE] Broadcasting REQUEST(ts=…) to peers …`
- `[REQUEST <-] from Node-…  ts=…` on the peer
- Either an immediate `[REPLY ->] sent to Node-…` or
  `[REQUEST] … DEFERRED reply to Node-…` (when the local node has priority).
- `[ACQUIRE] *** CS GRANTED — entering critical section ***` on exactly one
  node at a time.
- `[RELEASE] Exiting CS. Sending deferred REPLYs to: …`.

### Quick automated contention test

With Node 0 running, start:

```bash
python3 test_concurrent.py
```

This launches Alice and Bob in the same process (each with its own DME
instance and TCP listener) and has each of them fire three rapid `post`
calls. Inspect `node_1.log` and `node_2.log` afterwards to confirm that at
most one node is ever in state `HELD` at a time.

## Sample shared-file output (`chat.txt`)

```
12 Apr 09:01AM  Alice: Welcome to the team project
12 Apr 09:04AM  Bob: Thanks Alice - hope to work together
12 Apr 09:05AM  Alice: Bob, will send you the project outline by eod
```

## Ricart–Agrawala in one paragraph

Each user node keeps a Lamport logical clock and a state in
`{RELEASED, WANTED, HELD}`. To enter the critical section a node increments
its clock, broadcasts `REQUEST(ts, id)` to all peers, and waits for a
`REPLY` from each. A peer that receives a `REQUEST` replies immediately if
it is `RELEASED`, or when it is `WANTED` only if the incoming
`(ts, id)` is lexicographically smaller than its own; otherwise the reply is
**deferred** until the peer finishes its own critical section and sends a
`RELEASE`-time REPLY to everyone on its deferred queue. This guarantees
mutual exclusion without any centralized coordinator.
