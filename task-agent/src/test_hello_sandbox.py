"""
Step 2 — Test Hello World Sandbox Agent

Verifies:
  1. Agent runs without errors
  2. Agent response confirms the file was written
  3. Sandbox is isolated — outputs/hello.txt does NOT exist on the host filesystem
  4. Model and client are wired correctly (Gemini via Chat Completions)
  5. Session memory works — agent recalls prior turn in the same session

Rate limit note: Gemini free tier = 5 req/min. Tests share a single agent run
via a module-scoped fixture to minimise API calls (2 calls total for 5 tests).
"""

import os
from pathlib import Path

import pytest
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
set_tracing_export_api_key(os.environ["OPENAI_API_KEY"])


def build_agent() -> SandboxAgent:
    gemini_client = AsyncOpenAI(
        api_key=os.environ["GEMINI_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    model = OpenAIChatCompletionsModel(
        model="gemini-3.1-flash-lite",
        openai_client=gemini_client,
    )
    return SandboxAgent(
        name="Hello Sandbox",
        model=model,
        instructions=(
            "You are running inside an isolated sandbox workspace.\n"
            "When asked to say hello:\n"
            "1. Write exactly this line to outputs/hello.txt:\n"
            "   Hello from Gemini inside a sandbox!\n"
            "2. Run: cat outputs/hello.txt   to confirm the file was written.\n"
            "3. Report back what you wrote and confirm the file exists.\n"
            "When asked follow-up questions, use what you remember from the conversation."
        ),
        default_manifest=Manifest(entries={"outputs": Dir()}),
        capabilities=[Shell()],
    )


# --- Shared fixtures (one API call each, reused across multiple tests) ---

@pytest.fixture(scope="module")
def run_config():
    return RunConfig(sandbox=SandboxRunConfig(client=UnixLocalSandboxClient()))


@pytest.fixture(scope="module")
async def turn1_result(run_config):
    """Single Turn 1 run shared across tests 1–4."""
    result = await Runner.run(
        build_agent(),
        "Say hello and write it to a file.",
        run_config=run_config,
    )
    return result


@pytest.fixture(scope="module")
async def session_results(run_config):
    """Two-turn session run shared for the memory test."""
    agent = build_agent()
    session = SQLiteSession("test_session_memory")

    turn1 = await Runner.run(
        agent, "Say hello and write it to a file.",
        session=session, run_config=run_config,
    )
    turn2 = await Runner.run(
        agent, "What did you write in the file, and what was it called?",
        session=session, run_config=run_config,
    )
    return turn1, turn2


# --- Tests ---

def test_gemini_model_is_used():
    """No API call — just checks agent config."""
    agent = build_agent()
    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "gemini-3.1-flash-lite"


@pytest.mark.asyncio
async def test_agent_runs_without_error(turn1_result):
    assert turn1_result.final_output is not None
    assert len(turn1_result.final_output.strip()) > 0


@pytest.mark.asyncio
async def test_agent_confirms_file_written(turn1_result):
    output = turn1_result.final_output.lower()
    assert "hello.txt" in output
    assert "hello" in output


@pytest.mark.asyncio
async def test_sandbox_is_isolated_from_host(turn1_result):
    """File must NOT exist on the host — lives only inside the sandbox."""
    assert not Path("outputs/hello.txt").exists(), (
        "Sandbox leaked to host filesystem. Isolation is broken."
    )


@pytest.mark.asyncio
async def test_session_memory_across_turns(session_results):
    """Agent should remember what it wrote in Turn 1 when asked in Turn 2."""
    _, turn2 = session_results
    output = turn2.final_output.lower()
    assert "hello.txt" in output
    assert "hello" in output
