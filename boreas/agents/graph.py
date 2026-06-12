"""The agent society as one LangGraph graph, checkpointed to Postgres.

Sentinel -> (gate) -> Analyst -> (gate) -> Risk Officer -> (gate) -> Executor.
Every run is resumable and auditable: state checkpoints live in the same database
as everything else, and each cycle is also logged to agent_runs.
"""
from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from boreas import db
from boreas.agents import analyst as analyst_mod
from boreas.agents import executor as executor_mod
from boreas.agents import risk_officer
from boreas.agents import sentinel as sentinel_mod
from boreas.agents.schemas import Thesis
from boreas.config import settings
from boreas.features.frame import FeatureFrame

log = logging.getLogger("boreas.graph")


class CycleState(TypedDict, total=False):
    frame: dict  # FeatureFrame as dict (JSON-serializable for checkpointing)
    verdict: str
    verdict_reason: str
    thesis: dict | None
    pass_reason: str | None
    playbook_version: int
    approved: bool
    qty_mw: float
    risk_note: str
    thesis_id: str | None


async def _sentinel_node(state: CycleState) -> CycleState:
    frame = FeatureFrame.model_validate(state["frame"])
    verdict = await sentinel_mod.classify(frame)
    return {"verdict": verdict.level, "verdict_reason": verdict.reason}


async def _analyst_node(state: CycleState) -> CycleState:
    frame = FeatureFrame.model_validate(state["frame"])
    out, pb_version = await analyst_mod.analyze(frame)
    return {
        "thesis": out.thesis.model_dump(mode="json") if out.has_thesis and out.thesis else None,
        "pass_reason": out.pass_reason,
        "playbook_version": pb_version,
    }


async def _risk_node(state: CycleState) -> CycleState:
    thesis = Thesis.model_validate(state["thesis"])
    approved, qty, note = await risk_officer.review(thesis)
    return {"approved": approved, "qty_mw": qty, "risk_note": note}


async def _executor_node(state: CycleState) -> CycleState:
    frame = FeatureFrame.model_validate(state["frame"])
    thesis = Thesis.model_validate(state["thesis"])
    thesis_id = await executor_mod.execute(
        thesis, state["qty_mw"], state["risk_note"], frame, state["playbook_version"])
    return {"thesis_id": thesis_id}


def build_graph(checkpointer: Any | None = None):
    from langgraph.graph import END, StateGraph

    g = StateGraph(CycleState)
    g.add_node("sentinel", _sentinel_node)
    g.add_node("analyst", _analyst_node)
    g.add_node("risk", _risk_node)
    g.add_node("executor", _executor_node)

    g.set_entry_point("sentinel")
    g.add_conditional_edges(
        "sentinel", lambda s: "analyst" if s.get("verdict") == "act_worthy" else END,
        {"analyst": "analyst", END: END})
    g.add_conditional_edges(
        "analyst", lambda s: "risk" if s.get("thesis") else END,
        {"risk": "risk", END: END})
    g.add_conditional_edges(
        "risk", lambda s: "executor" if s.get("approved") else END,
        {"executor": "executor", END: END})
    g.add_edge("executor", END)
    return g.compile(checkpointer=checkpointer)


async def run_cycle(frame: FeatureFrame) -> CycleState:
    """Run one society cycle for a feature frame, checkpointed to Postgres."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    dsn = settings().database_url
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
        graph = build_graph(checkpointer=saver)
        config = {"configurable": {"thread_id": f"cycle-{frame.ts.isoformat()}"}}
        state: CycleState = await graph.ainvoke(
            {"frame": frame.model_dump(mode="json")}, config=config)

    p = await db.pool()
    await p.execute(
        """
        INSERT INTO agent_runs (kind, feature_ts, sentinel_verdict, detail, finished_at)
        VALUES ('cycle', $1, $2, $3::jsonb, now())
        """,
        frame.ts, state.get("verdict"),
        json.dumps({k: v for k, v in state.items() if k != "frame"}, default=str),
    )
    return state


async def run_cycle_plain(frame: FeatureFrame) -> CycleState:
    """Same pipeline without LangGraph/checkpointing — used by tests and as a fallback."""
    state: CycleState = {"frame": frame.model_dump(mode="json")}
    state.update(await _sentinel_node(state))
    if state.get("verdict") != "act_worthy":
        return state
    state.update(await _analyst_node(state))
    if not state.get("thesis"):
        return state
    state.update(await _risk_node(state))
    if not state.get("approved"):
        return state
    state.update(await _executor_node(state))
    return state
