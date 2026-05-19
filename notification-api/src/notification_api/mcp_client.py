from __future__ import annotations

import json
import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent

logger = logging.getLogger(__name__)


async def get_overdue_tasks(mcp_url: str, project: str) -> list[dict]:
    """Return overdue tasks for a project by calling project_view via MCP."""
    try:
        async with streamablehttp_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "project_view",
                    arguments={"project_name": project},
                )
                if not result.isError and result.content:
                    item = result.content[0]
                    text = item.text if isinstance(item, TextContent) else None
                    if text:
                        data = json.loads(text)
                        return data.get("overdue", [])
    except Exception:
        logger.exception("MCP call failed for project %r", project)
    return []
