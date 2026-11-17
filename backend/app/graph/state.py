"""
Shared state passed between LangGraph nodes for one per-video run.

Every agent function takes a PipelineState and returns an updated one — kept
as a plain TypedDict (not a pydantic model) since that's what LangGraph's
StateGraph expects natively.
"""
from typing import Any, Optional, TypedDict


class PipelineState(TypedDict, total=False):
    run_id: int
    channel: dict[str, Any]          # channel row as a dict (key, name, niche, subreddits, voices, daily_cap)

    candidates: list[dict[str, Any]]  # raw sourcing output, ranked+deduped by Curation into `story`
    story: Optional[dict[str, Any]]  # {source, source_id, title, content, score, curated}
    hook: Optional[str]
    script: Optional[str]
    qa_notes: list[str]

    voice_path: Optional[str]
    voice_used: Optional[str]  # which voice from channel's pool got picked this run
    background_clip: Optional[str]
    background_credit: Optional[str]  # CC BY attribution line, appended to the video description
    story_card_path: Optional[str]  # hook-duration overlay PNG (persona card)
    video_path: Optional[str]

    metadata: Optional[dict[str, Any]]  # {title, description, tags}
    compliance_ok: Optional[bool]
    compliance_notes: list[str]

    published: Optional[bool]
    youtube_video_id: Optional[str]

    stage_log: list[str]
    error: Optional[str]
