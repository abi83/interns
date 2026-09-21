"""Calls one gh-issues MCP tool the way the server would: `mcp_tool.py <name> <json kwargs>`.

Prints the tool's return value; an exception exits non-zero with its message.
"""

import json
import sys

import server

if __name__ == "__main__":
    tool = getattr(server, sys.argv[1])
    print(tool(**json.loads(sys.argv[2])))
