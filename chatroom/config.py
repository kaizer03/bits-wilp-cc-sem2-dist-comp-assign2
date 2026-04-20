# config.py -- shared configuration for all nodes

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

# RPC command types (user node -> file server)
RPC_VIEW = "VIEW"
RPC_POST = "POST"
