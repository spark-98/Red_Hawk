import os

import requests
from google.adk.tools import ToolContext


async def fire_at_target(attack_prompt: str, tool_context: ToolContext) -> dict:
    """Send one attack prompt to the target bot and return its raw response.

    Args:
      attack_prompt: The adversarial prompt to send to the target.
      tool_context: ADK tool context.

    Returns:
      {"attack_prompt": str, "target_response": str, "ok": bool}
    """
    target_url = os.environ.get("TARGET_URL", "http://127.0.0.1:5001/attack")
    try:
        resp = requests.post(
            target_url,
            json={"message": attack_prompt},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "attack_prompt": attack_prompt,
            "target_response": data.get("response", str(data)),
            "ok": True,
        }
    except Exception as exc:
        return {
            "attack_prompt": attack_prompt,
            "target_response": f"HTTP error: {exc}",
            "ok": False,
        }
