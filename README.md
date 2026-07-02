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

## Extending the security screen

`security.py` is intentionally simple (regex-based) so it's fast, free, and
fully unit-testable. If eval results show it's too strict or too loose on
real traffic, adjust `_PII_PATTERNS` / `_INJECTION_PATTERNS` and re-run
`smoke_test.py` — no LLM iteration loop needed for this layer.
