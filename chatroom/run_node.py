#!/usr/bin/env python3
# run_node.py -- Launches any of the three node roles.
# Usage:
#   python run_node.py 0          -> start file server (Node 0)
#   python run_node.py 1          -> start user Alice  (Node 1)
#   python run_node.py 2          -> start user Bob    (Node 2)

import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_node.py <node_id>")
        print("  node_id 0 -> File Server")
        print("  node_id 1 -> User Alice")
        print("  node_id 2 -> User Bob")
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
