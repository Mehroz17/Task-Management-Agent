from mcp.server.fastmcp import FastMCP
from task_mcp.tools import register_tools

mcp = FastMCP("task_mcp", host="0.0.0.0", port=8000, stateless_http=True)
register_tools(mcp)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
