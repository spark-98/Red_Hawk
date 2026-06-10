"""Red Hawk — one ADK turn runner.

Usage (from gemini-hackathon/):
    .venv\\Scripts\\python.exe agent/main.py
    .venv\\Scripts\\python.exe agent/main.py "Begin the red-team assessment."

Phoenix traces are sent automatically via instrumentation.setup_tracing().
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from google.adk.runners import InMemoryRunner
from google.genai import types

from instrumentation import setup_tracing
from red_team.agent import root_agent


async def run_turn(user_text: str) -> None:
    setup_tracing()
    app_name = "red_hawk"
    user_id = "local_user"
    session_id = secrets.token_hex(8)

    runner = InMemoryRunner(agent=root_agent, app_name=app_name)
    await runner.session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    print(f"[Red Hawk] session={session_id}")
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=user_text)]),
    ):
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text and part.text.strip():
                    print(part.text)


def main() -> None:
    msg = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Begin the red-team assessment. Run all three rounds and write your report."
    )
    asyncio.run(run_turn(msg))


if __name__ == "__main__":
    main()
