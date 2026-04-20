# dme.py -- Ricart-Agrawala Distributed Mutual Exclusion
# This module is INDEPENDENT of the chat application.
# It exposes two public methods: acquire() and release().

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
        acquire()  -- blocks until the CS is granted
        release()  -- exits CS, notifies deferred nodes
    """

    STATE_RELEASED = "RELEASED"   # not interested in CS
    STATE_WANTED   = "WANTED"     # waiting for all REPLYs
    STATE_HELD     = "HELD"       # inside CS

    def __init__(self, node_id: int):
        self.node_id = node_id
        self.log     = get_logger("DME", node_id)

        self.clock      = 0           # Lamport logical clock
        self.state      = self.STATE_RELEASED
        self.request_ts = None        # timestamp of our own last REQUEST

        self.reply_count    = 0       # replies received for current request
        # number of peers we must hear from before entering CS
        self.needed_replies = len([n for n in USER_NODES if n != self.node_id])
        self.deferred       = []      # list of node_ids whose REPLY we deferred

        self._lock     = threading.Lock()
        self._cs_event = threading.Event()   # set when all replies received

        # Start the DME listener thread
        self._server_thread = threading.Thread(
            target=self._listen, daemon=True, name=f"DME-listener-{node_id}"
        )
        self._server_thread.start()
        self.log.info(
            f"DME listener started on port {NODES[node_id]['port']}"
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                        #
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

        peers = [n for n in USER_NODES if n != self.node_id]
        self.log.info(
            f"[ACQUIRE] Broadcasting REQUEST(ts={req_clock}) to peers {peers}"
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

        self.log.info("[ACQUIRE] *** CS GRANTED -- entering critical section ***")

    def release(self):
        """Release the CS and flush deferred REPLYs."""
        with self._lock:
            self.state    = self.STATE_RELEASED
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
            self.log.debug(f"[RELEASE] Sent deferred REPLY -> Node-{peer_id}")

    # ------------------------------------------------------------------ #
    #  Internal -- message handling                                      #
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
        mtype   = msg["type"]
        peer_id = msg["node_id"]
        peer_ts = msg["clock"]

        with self._lock:
            # Update Lamport clock on receive
            self.clock = max(self.clock, peer_ts) + 1

        if mtype == MSG_REQUEST:
            self._on_request(peer_id, peer_ts)
        elif mtype == MSG_REPLY:
            self._on_reply(peer_id, peer_ts)

    def _on_request(self, peer_id: int, peer_ts: int):
        self.log.info(f"[REQUEST <-] from Node-{peer_id}  ts={peer_ts}")
        send_reply_now = False

        with self._lock:
            if self.state == self.STATE_HELD:
                # We are in CS -- must defer
                self.deferred.append(peer_id)
                self.log.debug(
                    f"[REQUEST] In CS -> DEFERRED reply to Node-{peer_id}"
                )
            elif self.state == self.STATE_WANTED:
                # We also want CS -- compare (timestamp, node_id); lower wins
                our_ts   = (self.request_ts, self.node_id)
                their_ts = (peer_ts, peer_id)
                if their_ts < our_ts:
                    # Peer has priority -> reply immediately
                    send_reply_now = True
                    self.log.debug(
                        f"[REQUEST] Peer Node-{peer_id} has priority "
                        f"({their_ts} < {our_ts}) -> immediate REPLY"
                    )
                else:
                    # We have priority -> defer
                    self.deferred.append(peer_id)
                    self.log.debug(
                        f"[REQUEST] We have priority ({our_ts} <= {their_ts}) "
                        f"-> DEFERRED reply to Node-{peer_id}"
                    )
            else:
                # STATE_RELEASED -- reply immediately
                send_reply_now = True
                self.log.debug(
                    f"[REQUEST] Not interested in CS -> immediate REPLY to Node-{peer_id}"
                )

        if send_reply_now:
            self._send_to(peer_id, {
                "type":    MSG_REPLY,
                "clock":   self._get_clock(),
                "node_id": self.node_id,
            })
            self.log.info(f"[REPLY ->] sent to Node-{peer_id}")

    def _on_reply(self, peer_id: int, peer_ts: int):
        self.log.info(f"[REPLY <-] from Node-{peer_id}  ts={peer_ts}")
        with self._lock:
            self.reply_count += 1
            self.log.debug(
                f"[REPLY] reply_count={self.reply_count}/{self.needed_replies}"
            )
            if self.reply_count >= self.needed_replies:
                self._cs_event.set()

    # ------------------------------------------------------------------ #
    #  Helpers                                                           #
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
        self.log.error(
            f"Failed to send to Node-{peer_id} after {retry} attempts"
        )
