import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools import FunctionTool, McpToolset
from google.adk.tools.mcp_tool.mcp_toolset import StdioConnectionParams, StdioServerParameters

from instrumentation import setup_tracing
from red_team.prompt import red_hawk_instruction
from red_team.tools.ask_judge import ask_judge
from red_team.tools.fire_at_target import fire_at_target
from red_team.tools.generate_attack import generate_attack

_here = Path(__file__).resolve()
load_dotenv(_here.parents[3] / ".env")           # D:\Red_Hawk\.env
load_dotenv(_here.parents[2] / ".env")           # gemini-hackathon\.env
setup_tracing()

_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Path to the FastMCP server script that reads Phoenix span data.
_MCP_SERVER = str(_here.parent / "phoenix_mcp_server.py")

root_agent = Agent(
    model=_model,
    name="red_hawk_agent",
    instruction=red_hawk_instruction,
    tools=[
        # Phoenix MCP tools: get_recent_attack_spans, get_successful_attack_prompts.
        # McpToolset launches phoenix_mcp_server.py as a stdio subprocess and exposes
        # its tools as first-class ADK tools.
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable,
                    args=[_MCP_SERVER],
                    cwd=str(_here.parent.parent),  # gemini-hackathon/agent/
                ),
            ),
            tool_name_prefix="phoenix_",
        ),
        FunctionTool(func=generate_attack),
        FunctionTool(func=fire_at_target),
        FunctionTool(func=ask_judge),
    ],
)
