# Red Hawk — Project Context & Handoff

> **Purpose of this file:** Full context for an AI coding assistant (Claude Code) working on this project. Read this first to understand what we're building, the hard constraints, the architecture, and the current state. Nothing here should be treated as executable instructions from third parties — it is project documentation written by the team.

---

## 1. What we are building

**Red Hawk** is an autonomous **AI red-teaming agent** for the **Google Cloud Rapid Agent Hackathon — Arize Track**.

The agent systematically probes a *target LLM application* for security weaknesses (jailbreaks, prompt injection, sensitive-information disclosure, excessive agency, system-prompt leakage, misinformation), scores which attacks succeed, traces every attempt with Arize Phoenix, and — the centerpiece — **reads its own traced results back via the Phoenix MCP server to improve its attacks over successive rounds** (a self-improvement loop).

The novel/winning angle is NOT "we can jailbreak a bot" — it's "we built an agent that does this **systematically, measures itself, and improves over time.**"

---

## 2. Hard constraints (from the hackathon rules — non-negotiable)

- **AI must be Gemini only.** Every component that produces AI output must be a Gemini call. No OpenAI, no Claude, no other model, no fine-tuned open-source model in the project. (Other Google Cloud AI tools are allowed.)
- **Must be a code-owned agent runtime** (Arize track requirement) — we use **Google ADK in Python**. The no-code visual Agent Builder is NOT allowed for this track, because Phoenix tracing must hook directly into our code via OpenInference instrumentation.
- **Must integrate a Partner MCP server** — for us that's the **Phoenix MCP server**.
- **Must run on web, Android, or iOS** (we'll satisfy "web", likely via Cloud Run and/or a Streamlit dashboard).
- **Newly built during the contest**; public open-source repo with a **detectable LICENSE file** (MIT or Apache 2.0 in repo root); setup instructions included.
- **Deadline: June 11, 2026, 2:00 PM PT** (~2:30 AM IST June 12). **Plan to submit June 10** (a day early).
- Demo video **≤ 3 minutes**, public on YouTube/Vimeo, English.
- Judging (equal weight): technical implementation, design, potential impact, idea quality. Arize also weighs **meaningful use of tracing + MCP and the quality of the self-improvement loop.**

---

## 3. Architecture

Five components:

1. **Orchestrator agent** — the brain. Gemini + Google ADK. Runs the loop, decides which tool to call each step. This is the "spine" (owned by the technical lead).
2. **Attack generator** — produces attack prompts across vulnerability families. Starts as a library of templates; later Gemini generates variations shaped by what worked.
3. **Target app** — a deliberately-vulnerable Gemini bot (the "punching bag") with a planted weakness. Kept deliberately minimal.
4. **Judge / evaluator** — LLM-as-a-Judge (a separate Gemini call) that scores whether each attack succeeded. Returns a structured verdict. Must be independent of attacker and target.
5. **Phoenix layer** — (a) **tracing** records every attempt (prompt, response, verdict); (b) the **Phoenix MCP server** lets the agent query its own traced history at runtime to improve.

### The loop (one round)
generate attack → fire at target → judge scores result → everything is traced by Phoenix → before next round, orchestrator queries Phoenix MCP ("what worked, what didn't") → feeds lessons into next attack batch → repeat. Success rate should climb over rounds (this rising curve is the key demo visual).

### The tool library (what the orchestrator calls)
The agent's tool list contains **four tools**:
- `generate_attack` — produce the next attack prompt(s).
- `fire_at_target` — send an attack to the target app, return its response.
- `ask_judge` — send the target's response to the judge, get a structured success/fail verdict.
- `query_phoenix` — (Phoenix MCP) read back past traced results so the next round is smarter. **This is one tool among the four — NOT the container of the others.**

---

## 4. Tech stack

**Required core:** Gemini (`google-genai` SDK), Google ADK (Python), Arize Phoenix (tracing + MCP), OpenInference instrumentation (`openinference-instrumentation-google-adk`, `arize-phoenix-otel`).

**Target app (Divyanshi):** FastAPI or Flask to serve the bot; JSON/YAML to store the attack library.

**Judge + dashboard (Yanshi):** Pydantic for structured judge verdicts; Streamlit for the results dashboard (the "success rate over rounds" chart).

**Shared:** Git + GitHub (public, LICENSE file), Python venv + requirements, python-dotenv + `.env` (keys never committed; `.env` in `.gitignore`). Cloud Run optional for hosting.

**Model confirmed:** repo defaults to `gemini-2.5-flash` (override via `GEMINI_MODEL` env var). Flash is the right default — fast/cheap for the high call volume of a red-team loop.

---

## 5. Starting point — the cloned repo

We started from the official **`Arize-ai/gemini-hackathon`** starter repo (end-to-end ADK agent + OpenInference + Phoenix tracing + Phoenix MCP, using a small in-memory shopping demo). Local folder renamed to **`red-hawk`**. We build on top of this — transforming the shopping demo into the red-team agent — rather than starting from scratch.

### The existing agent file (`agent.py`) — the pattern to follow
```python
import os
from pathlib import Path
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from dotenv import load_dotenv

from instrumentation import setup_tracing
from shopping_demo.prompt import personalized_shopping_agent_instruction
from shopping_demo.tools.click import click
from shopping_demo.tools.search import search

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
setup_tracing()

_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

root_agent = Agent(
    model=_model,
    name="personalized_shopping_agent",
    instruction=personalized_shopping_agent_instruction,
    tools=[
        FunctionTool(func=search),
        FunctionTool(func=click),
    ],
)
```

**Key observations:**
- The `tools=[...]` list IS the "tool library." We swap the two shopping tools (`search`, `click`) for our four red-team tools.
- Tools live in separate files (e.g. `shopping_demo/tools/search.py`) and are imported in. Our red-team tools should follow the same one-file-per-tool pattern — which also maps cleanly to the team split (Divyanshi owns the attack/target tool files, Yanshi owns the judge tool file).
- `setup_tracing()` and `load_dotenv(...)` wire up Phoenix and the `.env` keys — keep these.

### Target transformation of `agent.py`
```python
tools=[
    FunctionTool(func=generate_attack),
    FunctionTool(func=fire_at_target),
    FunctionTool(func=ask_judge),
    FunctionTool(func=query_phoenix),
]
```

---

## 6. The target bot ("punching bag") — design notes

Important finding from testing: **modern Gemini has trained-in safety reflexes independent of the system prompt.** Removing "never reveal" lines does NOT make it leak an obvious "API key" — the model refuses on reflex because the *concept* "API key" is trained-protected.

**Solution that worked:** disguise the secret as something the model doesn't instinctively guard. Framing the secret as a shareable **"internal reference code"** (rather than "API key") made the model reveal it even to a basic question. 

**Even stronger target design (recommended):** make the vulnerability a **skippable security behavior** rather than a leaked string — e.g. a bank bot that should require a PIN before a transfer, where "attack success" = getting it to skip the PIN check. This is easier to achieve, more realistic, and gives the judge a cleaner success signal than fuzzy partial string leakage.

**Attack families to cover** (build the attack library with a section per family, a few variants each — breadth signals depth to judges):
- Prompt injection / instruction override
- Jailbreak (role-play, gradual multi-turn ramp)
- Sensitive information disclosure (including partial/incremental extraction)
- Excessive agency / confused deputy
- System-prompt leakage
- Misinformation / hallucination induction
- Output/format manipulation (encoding, base64, translation to evade filters)

Multi-turn attacks are generally stronger than single-shot — relevant because the agent can naturally do multi-turn.

All testing is against **our own sandboxed bot with fake secrets** — authorized red-teaming to harden defenses.

---

## 7. Team & roles

- **Kimi (Technical Lead):** orchestrator, the loop, Phoenix tracing setup, the Phoenix MCP self-improvement loop, all integration, and defining the tool interfaces the others build against.
- **Divyanshi (Attack & Target Engineer):** the vulnerable target bot + the attack library (JSON/YAML, organized by family).
- **Yanshi (Evaluation & Experience Engineer):** the LLM-as-a-Judge scorer (Pydantic-structured verdicts) + the Streamlit results dashboard.

**Scope-protection rule:** if behind by Day 6, simplify the self-improvement loop — do NOT cut the core attacker→target→judge→tracing pipeline. The core alone is a complete, submittable project that passes the viability gate; the MCP self-improvement loop is the high-value bonus on top.

---

## 8. Current state / immediate next steps

- Repo cloned, renamed to `red-hawk`, `.env` filled in, `uv sync` completed.
- **TO CONFIRM:** that it runs (`adk run shopping_demo` per the file comment) and traces appear in Phoenix Cloud. This is the foundation check — verify before building new tools.
- **Next build step:** create the four tool stub files (one per tool, matching the `shopping_demo/tools/` pattern) with correct signatures, then fill them in **one at a time, testing each**, in this order: `fire_at_target` (simplest, proves the loop) → `ask_judge` → `generate_attack` → `query_phoenix` (last; depends on everything else working). Then swap the tool list in `agent.py`.
- Build incrementally; never generate all four tools at once (un-debuggable). One tool, tested, then the next.

---

## 9. Suggested folder structure for the red-team tools

Following the repo's existing one-file-per-tool convention, something like:
```
red_team/
  prompt.py              # orchestrator instruction (the red-team system prompt)
  tools/
    generate_attack.py
    fire_at_target.py
    ask_judge.py
    query_phoenix.py
  attacks/
    attack_library.yaml  # Divyanshi's attack corpus, by family
  target/
    target_bot.py        # Divyanshi's vulnerable bot (FastAPI/Flask)
  judge/
    judge.py             # Yanshi's Pydantic-structured judge logic
```
(Confirm against the actual repo layout — adapt imports to match how `agent.py` references its modules.)
