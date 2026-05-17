import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from openai import AsyncOpenAI
from pydantic import BaseModel

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

MCP_URL = os.environ.get("TASK_MCP_URL", "http://127.0.0.1:8000/mcp")

SESSIONS_DIR = Path("/tmp/sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _build_agent(mcp: MCPServerStreamableHttp) -> SandboxAgent:
    return SandboxAgent(
        name="Task MCP Sandbox",
        model=OpenAIChatCompletionsModel(
            model="gemini-3.1-flash-lite",
            openai_client=AsyncOpenAI(
                api_key=os.environ["GEMINI_API_KEY"],
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            ),
        ),
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
        mcp_servers=[mcp],
        default_manifest=Manifest(entries={"outputs": Dir()}),
        capabilities=[Shell()],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with MCPServerStreamableHttp(
        params=MCPServerStreamableHttpParams(url=MCP_URL)
    ) as mcp:
        app.state.agent = _build_agent(mcp)
        app.state.run_config = RunConfig(
            sandbox=SandboxRunConfig(client=UnixLocalSandboxClient())
        )
        yield


app = FastAPI(title="Task Agent API", version="0.1.0", lifespan=lifespan)


class AgentRunRequest(BaseModel):
    message: str
    session_id: str | None = None


class AgentRunResponse(BaseModel):
    session_id: str
    output: str
    new_session: bool


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "mcp_url": MCP_URL}


@app.post("/agent/run")
async def agent_run(body: AgentRunRequest) -> AgentRunResponse:
    new_session = body.session_id is None
    session_id = body.session_id or str(uuid.uuid4())
    result = await Runner.run(
        app.state.agent,
        body.message,
        session=SQLiteSession(session_id, db_path=SESSIONS_DIR / f"{session_id}.db"),
        run_config=app.state.run_config,
    )
    return AgentRunResponse(session_id=session_id, output=result.final_output, new_session=new_session)
