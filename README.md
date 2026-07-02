# Ambient Expense Agent (ADK 2.0)

A graph-based, event-driven agent that triages employee expense reports:
auto-approves anything under **$100**, routes anything at or above that
threshold to a **human-in-the-loop** manager review, and blocks payloads
that fail a PII/prompt-injection security screen — before any LLM is invoked.

```
START -> intake -> security_screen --clear--------> triage --auto_approve--> auto_approve -> respond
                        |                                `----human_review--> human_review -> respond
                        `----blocked-------------------------------------------> blocked -> respond
```

## What's in here

| File | Purpose |
|---|---|
| `agent.py` | The ADK 2.0 graph workflow (`root_agent`) + `App` wrapper. Real nodes, real routing, verified against the installed `google-adk` 2.3.0 API. |
| `security.py` | Deterministic PII redaction + prompt-injection detection. Pure Python, no LLM call — runs first, always. |
| `smoke_test.py` | Runs all three routes (auto-approve / human-review pause+resume / blocked) through the real `InMemoryRunner`. **Already passing** — see below. |
| `tests/eval/eval_config.json` | Rubric-based eval criteria (Routing Correctness, Security Containment), matching `agents-cli eval` / `adk eval` schema. |
| `tests/eval/evalsets/basic.evalset.json` | Four eval cases: low-value, high-value, PII-in-memo, prompt-injection. |
| `.env.example` | Copy to `.env` and add your `GOOGLE_API_KEY` (from Google AI Studio) or configure Vertex AI project/region instead. |

## What I already verified for you (no GCP account needed)

I installed `google-adk==2.3.0` and ran this exact code against the real
`Workflow`, `Runner`, and `RequestInput` classes — not simulated:

```
CASE 1 (low value)   -> status: auto_approved
CASE 2 (high value)  -> paused for human input: True
                      -> after manager approval -> status: approved
CASE 3 (prompt injection) -> status: blocked (before any LLM call)
```

Run it yourself any time with `python smoke_test.py` (no API key required —
every node on these paths is deterministic Python, no model calls happen).

## What you still need to do locally (needs Antigravity + your GCP project)

I don't have access to Antigravity, `gcloud`, or your Google Cloud
credentials from here, so these steps are yours to run, following the
codelab you linked:

1. **Drop this folder in** as your `ambient-expense-agent` project (or let
   Antigravity's `adk-scaffold` skill regenerate it — the graph/logic will
   match what's here either way).
2. `uv sync` / `uv lock` for a deterministic lockfile.
3. Fill in `.env` with a real `GOOGLE_API_KEY` (or Vertex AI project/region).
4. `agents-cli playground` — click through the flow interactively, confirm
   the $100 threshold and the human-in-the-loop pause behave as expected.
5. `agents-cli eval run` against `tests/eval/` — this is where the
   LLM-as-judge scoring (Routing Correctness / Security Containment,
   target 5.0 each per the codelab) actually runs; I can't invoke that
   without your API access.
6. Follow the linked codelab from "Generate Agent Runtime scaffolding"
   onward: `agents-cli deploy` to Agent Runtime, verify in Cloud Trace,
   check the enterprise Agent Registry.

## Extending the security screen

`security.py` is intentionally simple (regex-based) so it's fast, free, and
fully unit-testable. If eval results show it's too strict or too loose on
real traffic, adjust `_PII_PATTERNS` / `_INJECTION_PATTERNS` and re-run
`smoke_test.py` — no LLM iteration loop needed for this layer.
