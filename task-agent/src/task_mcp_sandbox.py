"""
Step 3 — SandboxAgent connected to task-mcp-server

What this demonstrates:
  - SandboxAgent discovering and calling real MCP tools over HTTP
  - Agent creates a task in task-mcp-server via task_create tool
  - Agent writes a summary of what it did to outputs/summary.txt
  - Same Gemini model + tracing + session as Step 1
"""

import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

from agents import (
    OpenAIChatCompletionsModel,
    RunConfig,
    Runner,
    SQLiteSession,
    set_tracing_export_api_key,
)
from agents.mcp import MCPServerStreamableHttp, MCPServerStreamableHttpParams
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Shell
from agents.sandbox.entries import Dir
from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient

load_dotenv()

set_tracing_export_api_key(os.environ["OPENAI_API_KEY"])


def build_model() -> OpenAIChatCompletionsModel:
    gemini_client = AsyncOpenAI(
        api_key=os.environ["GEMINI_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    return OpenAIChatCompletionsModel(
        model="gemini-3.1-flash-lite",
        openai_client=gemini_client,
    )


def build_agent(mcp_server: MCPServerStreamableHttp) -> SandboxAgent:
    return SandboxAgent(
        name="Task MCP Sandbox",
        model=build_model(),
        instructions=(
            "You are a task management agent running in an isolated sandbox.\n"
            "You have access to a task management MCP server with tools like "
            "task_create, task_get, and project_view.\n"
            "\n"
            "When asked to create a task:\n"
            "1. Call task_create with the provided details.\n"
            "2. Call task_get with the returned task_id to confirm it was saved.\n"
            "3. Write a one-line summary to outputs/summary.txt:\n"
            "   echo 'Created task: <title> (id: <task_id>)' > outputs/summary.txt\n"
            "4. Run: cat outputs/summary.txt  to confirm the write.\n"
            "5. Report back the task id, title, and confirm the summary file was written.\n"
            "\n"
            "When asked to list tasks in a project, call project_view with the project name."
        ),
        mcp_servers=[mcp_server],
        default_manifest=Manifest(entries={"outputs": Dir()}),
        capabilities=[Shell()],
    )


async def main() -> None:
    mcp_url = os.environ.get("TASK_MCP_URL", "http://127.0.0.1:8000/mcp")

    print("=" * 55)
    print("  Step 3 — SandboxAgent + task-mcp-server")
    print(f"  MCP URL: {mcp_url}")
    print("  Model  : gemini-3.1-flash-lite")
    print("=" * 55)
    print()

    async with MCPServerStreamableHttp(params=MCPServerStreamableHttpParams(url=mcp_url)) as mcp_server:
        agent = build_agent(mcp_server)
        session = SQLiteSession("task_mcp_sandbox_session")
        run_config = RunConfig(sandbox=SandboxRunConfig(client=UnixLocalSandboxClient()))

        print("Turn 1: Create a task via MCP")
        print("-" * 55)
        result = await Runner.run(
            agent,
            (
                "Create a task titled 'Write Step 3 integration' in project 'task-agent', "
                "with description 'Connect SandboxAgent to task-mcp-server and verify MCP tools work', "
                "priority high."
            ),
            session=session,
            run_config=run_config,
        )
        print(result.final_output)
        print()

        print("Turn 2: List tasks in the project")
        print("-" * 55)
        result = await Runner.run(
            agent,
            "Show me all tasks in the 'task-agent' project.",
            session=session,
            run_config=run_config,
        )
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
