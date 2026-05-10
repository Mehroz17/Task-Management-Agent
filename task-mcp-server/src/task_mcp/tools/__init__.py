from mcp.server.fastmcp import FastMCP
from task_mcp.tools.task_create import task_create
from task_mcp.tools.task_get import task_get
from task_mcp.tools.task_transition import task_transition
from task_mcp.tools.task_update import task_update
from task_mcp.tools.task_delete import task_delete
from task_mcp.tools.project_view import project_view


def register_tools(mcp: FastMCP) -> None:
    mcp.tool(name="task_create", description="Create a fully set-up task in one call")(task_create)
    mcp.tool(name="task_get", description="Get full detail of a single task including comments")(task_get)
    mcp.tool(name="task_transition", description="Change task status with a required note explaining why")(task_transition)
    mcp.tool(name="task_update", description="Edit task fields and/or add a comment in one call")(task_update)
    mcp.tool(name="task_delete", description="Permanently delete a task")(task_delete)
    mcp.tool(name="project_view", description="Get project health: totals, status breakdown, overdue, blocked, by assignee")(project_view)
