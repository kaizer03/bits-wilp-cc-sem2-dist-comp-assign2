# test_concurrent.py -- Simulate concurrent posts from Alice and Bob
# Run this INSTEAD of the interactive CLI to stress-test the DME algorithm.
# Requires Node 0 (file server) to already be running:
#
#   Terminal 1:  python run_node.py 0
#   Terminal 2:  python test_concurrent.py
#
# Inspect node_1.log and node_2.log afterwards to verify that:
#   - Both nodes broadcast REQUEST with Lamport timestamps.
#   - The lower (timestamp, node_id) pair always wins.
#   - The losing node's REPLY is deferred until the winner RELEASES.
#   - No two nodes are ever "HELD" (in CS) at the same time.

import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import USER_NODES, NODES
from dme import RicartAgrawala
from chat_app import cmd_post, cmd_view
from logger import get_logger


POSTS_PER_NODE = 3


def node_worker(node_id: int):
    username = NODES[node_id]["username"]
    log = get_logger("TestWorker", node_id)
    dme = RicartAgrawala(node_id)

    # Let all DME listeners start on every node.
    time.sleep(1.5)

    for i in range(POSTS_PER_NODE):
        msg = f"Test message {i + 1} from {username}"
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
    tester_log = get_logger("Test", 99)
    cmd_view(99, "Tester", tester_log)
    print("\nCheck node_1.log and node_2.log to verify DME correctness.")
