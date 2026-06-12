"""The playbook: a versioned markdown file of learned rules, evolved by the Reflector.

Small (non-structural) diffs auto-merge; structural ones wait for human approval, PR-style.
"""
from __future__ import annotations

import logging

from boreas import db
from boreas.agents.schemas import PlaybookDiff

log = logging.getLogger("boreas.playbook")

SEED = """\
# BOREAS Playbook

## Entry rules
- Only trade when the divergence z-score exceeds 2.0 and the merit-order regime is steep,
  or when forecast error has trended one direction for 3+ hours into a ramp window.
- Evening ramp quarter-hours (qh 64-80) are the highest-conviction window for wind-error theses.

## Sizing rules
- Confidence above 0.75 requires an explicit falsifier that can fire before delivery.

## Exit / settlement rules
- A fired falsifier invalidates the thesis regardless of unrealized P&L direction.
"""


async def current() -> tuple[int, str]:
    p = await db.pool()
    rec = await p.fetchrow(
        "SELECT version, content FROM playbook_versions WHERE approved ORDER BY version DESC LIMIT 1")
    if rec is None:
        await p.execute(
            "INSERT INTO playbook_versions (content, rationale) VALUES ($1, 'seed playbook')", SEED)
        return await current()
    return rec["version"], rec["content"]


def apply_diff(content: str, diff: PlaybookDiff) -> str:
    out = content
    for rule in diff.retired_rules:
        out = "\n".join(line for line in out.splitlines() if rule.strip() not in line)
    if diff.new_rules:
        bullets = "\n".join(f"- {r.lstrip('- ').strip()}" for r in diff.new_rules)
        out = out.rstrip() + "\n\n## Learned " + "rules\n" + bullets + "\n"
    return out


async def propose(diff: PlaybookDiff) -> int:
    """Append a new version. Auto-merges unless structural (then approved=False, awaits human)."""
    version, content = await current()
    new_content = apply_diff(content, diff)
    auto = not diff.structural
    p = await db.pool()
    new_version = await p.fetchval(
        """
        INSERT INTO playbook_versions (content, diff, rationale, auto_merged, approved)
        VALUES ($1, $2, $3, $4, $4) RETURNING version
        """,
        new_content,
        "\n".join([f"+ {r}" for r in diff.new_rules] + [f"- {r}" for r in diff.retired_rules]),
        diff.rationale, auto,
    )
    log.info("playbook v%d proposed (structural=%s, auto_merged=%s)", new_version, diff.structural, auto)
    return new_version


async def approve(version: int) -> None:
    p = await db.pool()
    await p.execute("UPDATE playbook_versions SET approved = TRUE WHERE version = $1", version)
