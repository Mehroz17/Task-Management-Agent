"""
Step 1 — Hello World Sandbox Agent (with tracing + session)

What this demonstrates:
  - Gemini 3-flash-preview via OpenAI-compatible endpoint
  - SandboxAgent in an isolated local workspace (Shell only — Gemini compatible)
  - OpenAI tracing — traces visible at platform.openai.com/traces
  - SQLiteSession — multi-turn memory, agent remembers prior conversation turns
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
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Shell
from agents.sandbox.entries import Dir
from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient

load_dotenv()

# Tracing — model runs on Gemini, traces still go to OpenAI dashboard
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


manifest = Manifest(entries={"outputs": Dir()})

agent = SandboxAgent(
    name="Hello Sandbox",
    model=build_model(),
    instructions=(
        "You are running inside an isolated sandbox workspace.\n"
        "When asked to say hello:\n"
        "1. Write exactly this line to outputs/hello.txt:\n"
        "   Hello from Gemini inside a sandbox!\n"
        "2. Run: cat outputs/hello.txt   to confirm the file was written.\n"
        "3. Report back what you wrote and confirm the file exists.\n"
        "When asked follow-up questions, use what you remember from earlier in the conversation."
    ),
    default_manifest=manifest,
    capabilities=[
        # Filesystem() uses SandboxApplyPatchTool (CustomTool) — rejected by the
        # Chat Completions converter used for Gemini. Shell() uses only FunctionTool
        # subclasses so files are written via shell commands (echo/redirect) instead.
        Shell(),
    ],
)


async def main() -> None:
    # SQLiteSession persists conversation history to a local .db file.
    # The same session_id picks up the full history on the next run.
    session = SQLiteSession("hello_sandbox_session")

    print("=" * 55)
    print("  Step 1 — Hello World Sandbox Agent")
    print("  Model  : gemini-3.1-flash-lite")
    print("  Tracing: OpenAI dashboard (platform.openai.com/traces)")
    print("  Session: hello_sandbox_session (SQLite)")
    print("=" * 55)
    print()

    run_config = RunConfig(sandbox=SandboxRunConfig(client=UnixLocalSandboxClient()))

    # Turn 1
    print("Turn 1: Say hello and write it to a file")
    print("-" * 55)
    result = await Runner.run(
        agent,
        "Say hello and write it to a file.",
        session=session,
        run_config=run_config,
    )
    print(result.final_output)
    print()

    # Turn 2 — tests session memory: agent should remember it already wrote the file
    print("Turn 2: What did you write in the file?")
    print("-" * 55)
    result = await Runner.run(
        agent,
        "What did you write in the file, and what was it called?",
        session=session,
        run_config=run_config,
    )
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
