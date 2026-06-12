"""Structured outputs for the agent society — validated by the API, not parsed by hope."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SentinelVerdict(BaseModel):
    level: Literal["nothing", "interesting", "act_worthy"]
    reason: str = Field(description="One sentence: which signal drives the classification")


class Thesis(BaseModel):
    strategy: Literal["da_curve", "da_rebap_spread"]
    direction: Literal["long", "short"]
    delivery_date: str = Field(description="ISO date of the delivery day, e.g. 2026-06-14")
    qh_indices: list[int] = Field(
        description="Affected quarter-hours of the delivery day, 0..95 (e.g. evening ramp = 68..76)")
    expected_move_eur_mwh: float = Field(
        description="Expected price move vs reference, EUR/MWh, signed in trade direction")
    confidence: float = Field(ge=0.0, le=1.0)
    falsifier: str = Field(
        description="Concrete observable that kills the thesis, e.g. '18z ICON run revises wind up 3+ GW'")
    rationale: str = Field(description="The causal chain, 3-6 sentences, referencing the features")


class AnalystOutput(BaseModel):
    has_thesis: bool
    thesis: Thesis | None = None
    pass_reason: str | None = Field(default=None, description="If no thesis, why the setup is not tradeable")


class RiskCommentary(BaseModel):
    concerns: list[str] = Field(description="Risks the sizing should respect, max 3")
    proceed: bool = Field(description="Whether the thesis is sane to trade at the computed size")


class PlaybookDiff(BaseModel):
    structural: bool = Field(
        description="True if the change alters strategy/risk logic rather than adding an observation")
    rationale: str
    new_rules: list[str] = Field(description="Rules to append, each a single markdown bullet")
    retired_rules: list[str] = Field(default_factory=list,
                                     description="Existing rules to remove, quoted verbatim")


class Reflection(BaseModel):
    attribution: Literal["forecast_wrong", "sizing_wrong", "falsifier_ignored", "thesis_right",
                         "noise", "data_issue"]
    post_mortem: str = Field(description="Journal entry: what happened vs what the thesis predicted")
    playbook_diff: PlaybookDiff | None = None
