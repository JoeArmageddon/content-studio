"""
Compliance/Repost-Guard Agent — Milestone 6 (full implementation).

Final gate before publish:
  - Blocks on a policy-risk phrase flagged by Script QA (added early, in
    Milestone 3, as a safety net once real content generation existed).
  - Flags (does NOT block) a background clip that repeats one from the
    channel's last few videos — background-footage reuse is intentional in
    this pipeline (Background-Sourcing Agent caches and reuses a small
    clip pool on purpose, for cost/API-usage reasons), so this is a
    visibility note, not a publish-blocker. Only exact-story reuse
    (handled earlier, by Curation's dedupe check) and policy-risk content
    actually block.
"""
from app.core.db import SessionLocal
from app.core.models import Video
from app.graph.state import PipelineState

_RECENT_VIDEOS_TO_CHECK = 5


def run(state: PipelineState) -> PipelineState:
    qa_notes = state.get("qa_notes") or []
    policy_risk = any("policy-risk" in note.lower() for note in qa_notes)

    background_clip = state.get("background_clip")
    channel = state.get("channel", {})
    channel_id = channel.get("id")

    background_repeat = False
    if background_clip and channel_id:
        db = SessionLocal()
        try:
            recent = (
                db.query(Video)
                .filter(Video.channel_id == channel_id)
                .order_by(Video.id.desc())
                .limit(_RECENT_VIDEOS_TO_CHECK)
                .all()
            )
            background_repeat = any(v.background_clip == background_clip for v in recent)
        finally:
            db.close()

    notes = list(state.get("compliance_notes") or [])
    if policy_risk:
        notes.append("Blocked: Script QA flagged a policy-risk phrase.")
    if background_repeat:
        notes.append(
            f"Note: background clip repeats one from the last {_RECENT_VIDEOS_TO_CHECK} videos "
            "(not blocking — background reuse is expected)."
        )

    state["compliance_ok"] = not policy_risk
    state["compliance_notes"] = notes
    state.setdefault("stage_log", []).append("compliance")
    return state
