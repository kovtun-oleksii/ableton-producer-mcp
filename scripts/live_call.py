"""Send one command straight to the AbletonMCP Remote Script and print the reply.

Bypasses the MCP server, for smoke-testing Remote Script changes in a running
Live. Usage:

    python scripts/live_call.py get_script_info
    python scripts/live_call.py get_clip_automation '{"track_index": 0, "clip_index": 0, ...}'
"""
import json
import os
import socket
import sys

HOST = os.environ.get("ABLETON_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ABLETON_MCP_PORT", "9877"))


def call(command_type, params=None, timeout=70.0):
    with socket.create_connection((HOST, PORT), timeout=timeout) as sock:
        sock.sendall(json.dumps({"type": command_type, "params": params or {}}).encode("utf-8"))
        buffer = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buffer += chunk
            try:
                return json.loads(buffer.decode("utf-8"))
            except ValueError:
                continue
    raise ConnectionError("Connection closed before a complete reply arrived")


if __name__ == "__main__":
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(call(sys.argv[1], params), indent=2))
