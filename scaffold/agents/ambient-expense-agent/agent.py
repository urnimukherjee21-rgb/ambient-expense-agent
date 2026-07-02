"""Ambient Expense Agent — ADK 2.0 graph workflow.

Flow:
    START -> intake -> security_screen --clear--> triage --auto_approve--> auto_approve -> respond
                            |                          `--human_review--> human_review -> respond
                            `--blocked--> blocked -> respond

- security_screen redacts PII and short-circuits prompt-injection attempts
  BEFORE any LLM is invoked (see security.py).
- triage applies the $100 auto-approval threshold.
- human_review pauses the workflow (RequestInput) for a manager decision on
  anything >= $100 — this is the human-in-the-loop step.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from google.adk.agents.context import Context
from google.adk.agents.llm_agent import Agent
from google.adk.apps import App
from google.adk.events.request_input import RequestInput
from google.adk.workflow import START, Workflow, node

from security import screen_expense_payload

AUTO_APPROVAL_THRESHOLD_USD = 100.0


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class ExpenseReport(BaseModel):
    employee: str
    category: str
    amount_usd: float
    memo: str = ""


class ExpenseDecision(BaseModel):
    status: Literal["auto_approved", "approved", "rejected", "blocked"]
    amount_usd: float
    reason: str
    reviewer: Optional[str] = None


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------

@node
async def intake(ctx: Context, node_input: dict) -> ExpenseReport:
    """Parse and validate the raw incoming expense payload."""
    report = ExpenseReport.model_validate(node_input)
    ctx.state["report"] = report.model_dump()
    return report


@node
async def security_screen(ctx: Context, node_input: ExpenseReport) -> None:
    """Redact PII and check for prompt-injection before any LLM sees the payload.

    Sets ctx.route to "clear" or "blocked", consumed by the RoutingMap.
    """
    result = screen_expense_payload(node_input.model_dump())
    ctx.state["security_redactions"] = result.redactions
    ctx.state["clean_report"] = result.clean_payload
    if result.injection_detected:
        ctx.state["block_reason"] = result.injection_reason
    ctx.route = result.route


@node
async def triage(ctx: Context, node_input: None) -> None:
    """Apply the $100 auto-approval threshold. Sets ctx.route to the route key."""
    clean = ctx.state["clean_report"]
    amount = clean["amount_usd"]
    ctx.state["triage_amount"] = amount
    ctx.route = "auto_approve" if amount < AUTO_APPROVAL_THRESHOLD_USD else "human_review"


@node
async def auto_approve(ctx: Context, node_input: None) -> ExpenseDecision:
    clean = ctx.state["clean_report"]
    return ExpenseDecision(
        status="auto_approved",
        amount_usd=clean["amount_usd"],
        reason=f"Below the ${AUTO_APPROVAL_THRESHOLD_USD:.0f} auto-approval threshold.",
    )


@node(rerun_on_resume=True)
async def human_review(ctx: Context, node_input: None):
    """Pause the workflow and wait for a manager's approve/reject decision.

    On first run, yields a RequestInput -> the graph interrupts here.
    On resume, ctx.resume_inputs carries the manager's response.
    """
    clean = ctx.state["clean_report"]

    if ctx.resume_inputs:
        decision = next(iter(ctx.resume_inputs.values()))
        approved = bool(decision.get("approved"))
        reviewer = decision.get("reviewer", "unknown_manager")
        yield ExpenseDecision(
            status="approved" if approved else "rejected",
            amount_usd=clean["amount_usd"],
            reason=decision.get("comment", "Manager decision."),
            reviewer=reviewer,
        )
        return

    yield RequestInput(
        message=(
            f"Expense of ${clean['amount_usd']:.2f} ({clean['category']}) from "
            f"{clean['employee']} exceeds the ${AUTO_APPROVAL_THRESHOLD_USD:.0f} "
            "auto-approval threshold and requires manager review."
        ),
        response_schema={
            "type": "object",
            "properties": {
                "approved": {"type": "boolean"},
                "reviewer": {"type": "string"},
                "comment": {"type": "string"},
            },
            "required": ["approved", "reviewer"],
        },
    )


@node
async def blocked(ctx: Context, node_input: None) -> ExpenseDecision:
    clean = ctx.state.get("clean_report", {})
    return ExpenseDecision(
        status="blocked",
        amount_usd=clean.get("amount_usd", 0.0),
        reason=f"Security screen rejected this submission: {ctx.state.get('block_reason')}",
    )


@node
async def respond(ctx: Context, node_input: ExpenseDecision) -> ExpenseDecision:
    ctx.state["final_decision"] = node_input.model_dump()
    return node_input


# --------------------------------------------------------------------------
# Optional: LLM sub-agent for risk-analysis commentary shown to the manager
# alongside the human_review pause. Not required for routing correctness,
# purely additive context. Swap the model via .env / agents-cli config.
# --------------------------------------------------------------------------

risk_analyst = Agent(
    model="gemini-2.5-flash",
    name="risk_analyst",
    description="Summarizes risk factors on a high-value expense for a human reviewer.",
    instruction=(
        "You are given a redacted expense report (PII already stripped). "
        "In 2-3 sentences, summarize risk factors a manager should consider "
        "(category norms, amount relative to typical spend, anything unusual "
        "in the memo). Never invent facts not present in the report. Do not "
        "make an approval decision yourself — that is the human's job."
    ),
)


root_agent = Workflow(
    name="ambient_expense_agent",
    description=(
        "Triages employee expense reports: auto-approves items under "
        f"${AUTO_APPROVAL_THRESHOLD_USD:.0f}, routes larger ones to human-in-the-loop "
        "review, and blocks payloads that fail a PII/prompt-injection security screen."
    ),
    input_schema=dict,
    output_schema=ExpenseDecision,
    edges=[
        (START, intake, security_screen),
        (security_screen, {"clear": triage, "blocked": blocked}),
        (triage, {"auto_approve": auto_approve, "human_review": human_review}),
        (auto_approve, respond),
        (human_review, respond),
        (blocked, respond),
    ],
)

app = App(name="ambient_expense_agent", root_agent=root_agent)
