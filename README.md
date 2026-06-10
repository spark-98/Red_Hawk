# Red Hawk 🦅

**Autonomous AI red-teaming agent that probes a target LLM, scores every attack with an
independent judge, traces all of it to Arize Phoenix, and reads its own traces back via the
Phoenix MCP server to improve over successive rounds.**

Built for the **Google Cloud Rapid Agent Hackathon — Arize Track**. Sits at the
AI + cybersecurity intersection: it doesn't just jailbreak a bot, it does so *systematically,
measures itself, and improves over time* — a closed self-improvement loop.

---

## Why

As LLM applications ship to production, they need continuous adversarial testing. Manual
red-teaming doesn't scale. Red Hawk automates the full loop — generate attack → fire at target
→ judge the result → trace it → learn from past rounds → attack smarter — and surfaces a rising
success-rate curve that quantifies how an attacker improves against a given target.

## Architecture

Five components wired through Google ADK:

1. **Orchestrator agent** (`agent/red_team/agent.py`) — Gemini + ADK. Runs the 3-round loop and
   decides which tool to call each step.
2. **Attack generator** (`generate_attack`) — draws fresh prompts from a YAML library of 7
   vulnerability families, filtering out what was already tried.
3. **Target bot** (`target_bot.py`) — a deliberately vulnerable Flask + Gemini app with a planted
   secret flag (`FLAG{RED_HAWK_TARGET_COMPROMISED}`). The "punching bag."
4. **Judge** (`ask_judge`) — an independent Gemini call returning a Pydantic-structured verdict
   (`success`, `severity` 0–10, `reason`). Isolated from attacker and target so it can't be biased.
5. **Phoenix layer** — (a) OpenInference tracing records every attempt; (b) the **Phoenix MCP
   server** (`phoenix_mcp_server.py`) lets the agent query its own traced history at runtime.

### The loop (one round)

```
generate_attack → fire_at_target → ask_judge → [Phoenix traces everything]
        ↑                                                    │
        └──── phoenix_get_successful_attack_prompts ─────────┘
              (read what worked before the next round)
```

The agent's tool list is exactly four logical tools: `generate_attack`, `fire_at_target`,
`ask_judge`, and the Phoenix MCP query tools (`phoenix_get_recent_attack_spans`,
`phoenix_get_successful_attack_prompts`).

## Attack families

`jailbreak`, `injection`, `disclosure`, `excessive_agency`, `system_prompt_leakage`,
`misinformation`, `output_manipulation` — see `agent/red_team/attacks/attack_library.yaml`.

---

## Prerequisites

- Python 3.10–3.12 and [uv](https://docs.astral.sh/uv/)
- Google auth for Gemini — **Vertex AI / ADC** (recommended): `gcloud auth application-default login`
  plus `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION`; **or** a `GOOGLE_API_KEY`
- A Phoenix Cloud API key ([app.phoenix.arize.com](https://app.phoenix.arize.com))

## Setup

```bash
cd gemini-hackathon
cp .env.example .env
# Edit .env:
#   - Vertex path: GOOGLE_GENAI_USE_VERTEXAI=1, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION
#   - PHOENIX_API_KEY and PHOENIX_COLLECTOR_ENDPOINT (Hostname incl. /s/<space>)
uv sync
gcloud auth application-default login   # if using the Vertex path
```

## Run

All commands below assume the venv at `gemini-hackathon/.venv`.

**1. Start the target bot** (separate terminal, from repo root):
```bash
gemini-hackathon/.venv/Scripts/python.exe target_bot.py     # serves http://127.0.0.1:5001
```

**2. Run the orchestrator** (one full 3-round assessment, from `gemini-hackathon/`):
```bash
.venv/Scripts/python.exe agent/main.py
# or pass your own kickoff message:
.venv/Scripts/python.exe agent/main.py "Begin the red-team assessment."
```

**3. Inspect traces** — open Phoenix; project defaults to `PHOENIX_PROJECT_NAME`
(`gemini-hackathon`). You'll see LLM and tool spans for every attack, response, and verdict.

## End-to-end smoke test

A single script exercises all six stages (target health/attack, `generate_attack`,
`fire_at_target`, `ask_judge`, and a full 3-round orchestrator turn). It starts and stops the
target bot for you:

```bash
gemini-hackathon/.venv/Scripts/python.exe smoke_test_e2e.py
```

Expect `6/6 passed`. (The orchestrator runs with thinking disabled so the 3-round loop completes
deterministically; the judge uses a Vertex-published model — see `.env` notes.)

## Layout

| Path | Purpose |
| ---- | ------- |
| `target_bot.py` | Vulnerable Flask + Gemini target with planted flag |
| `smoke_test_e2e.py` | 6-stage end-to-end smoke test |
| `gemini-hackathon/agent/main.py` | One-shot orchestrator runner with tracing |
| `gemini-hackathon/agent/instrumentation.py` | `phoenix.otel.register(..., auto_instrument=True)` |
| `gemini-hackathon/agent/red_team/agent.py` | ADK `root_agent` + tool wiring |
| `gemini-hackathon/agent/red_team/prompt.py` | Orchestrator instruction (the loop) |
| `gemini-hackathon/agent/red_team/tools/` | `generate_attack`, `fire_at_target`, `ask_judge` |
| `gemini-hackathon/agent/red_team/phoenix_mcp_server.py` | FastMCP server exposing Phoenix span history |
| `gemini-hackathon/agent/red_team/attacks/attack_library.yaml` | Attack corpus by family |

## Team

- **Dhairya (Kimi)** — Technical Lead / Architect: orchestrator, Phoenix tracing, MCP self-improvement loop
- **Divyanshi** — Attack & Target Engineer: target bot, attack library
- **Yanshi** — Evaluation & Experience Engineer: judge rubric, results dashboard (frontend)

## Safety

All testing runs against our own sandboxed bot with a fake planted flag — authorized
red-teaming to harden defenses, not to attack third-party systems.

## License

Apache-2.0 — see [LICENSE](LICENSE).
