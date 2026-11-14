"""``python -m quickalignment.agent``: the MCP server on stdin/stdout (as ``python -m arpes_viewer.agent``)."""
import sys

from quickalignment.agent.mcp_server import main

sys.exit(main())
