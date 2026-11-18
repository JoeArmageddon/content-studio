"""
Builds the per-video LangGraph pipeline.

Linear for now (Milestone 1) — Curation/Compliance can later add
conditional edges (e.g. loop back to Sourcing on a duplicate, or short-
circuit Publisher on a compliance failure) once Milestone 2/6 logic is real.
"""
from langgraph.graph import END, StateGraph

from app.agents import (
    background_sourcing_agent,
    compliance_agent,
    curation_agent,
    hook_agent,
    metadata_agent,
    publisher_agent,
    script_qa_agent,
    scriptwriter_agent,
    sourcing_agent,
    voice_agent,
)
from app.core.config import DATA_DIR
from app.graph.state import PipelineState
from app.services.ffmpeg_render import assemble_video
from app.services.story_card_renderer import render_card


def _story_card_node(state: PipelineState) -> PipelineState:
    channel = state.get("channel", {})
    persona = channel.get("persona") or {}
    key = channel.get("key", "unknown")
    run_id = state.get("run_id", "x")
    out_path = str(DATA_DIR / "story_cards" / f"{key}_{run_id}.png")
    try:
        state["story_card_path"] = render_card(state.get("hook", ""), persona, out_path, channel=channel, story=state.get("story"))
    except Exception as exc:  # noqa: BLE001 — story-card failure shouldn't crash the run
        state["story_card_path"] = None
        state["error"] = f"Story-card rendering failed: {exc}"
    state.setdefault("stage_log", []).append("story_card")
    return state


def _assemble_node(state: PipelineState) -> PipelineState:
    try:
        state["video_path"] = assemble_video(state)
    except Exception as exc:  # noqa: BLE001 — assembly failure shouldn't crash the run
        state["video_path"] = None
        state["error"] = f"Video assembly failed: {exc}"
    state.setdefault("stage_log", []).append("assemble")
    return state


def build_pipeline():
    graph = StateGraph(PipelineState)

    graph.add_node("source", sourcing_agent.run)
    graph.add_node("curate", curation_agent.run)
    graph.add_node("hook", hook_agent.run)
    graph.add_node("script", scriptwriter_agent.run)
    graph.add_node("script_qa", script_qa_agent.run)
    graph.add_node("voice", voice_agent.run)
    graph.add_node("background", background_sourcing_agent.run)
    graph.add_node("story_card", _story_card_node)
    graph.add_node("assemble", _assemble_node)
    graph.add_node("metadata", metadata_agent.run)
    graph.add_node("compliance", compliance_agent.run)
    graph.add_node("publish", publisher_agent.run)

    graph.set_entry_point("source")
    graph.add_edge("source", "curate")
    graph.add_edge("curate", "hook")
    graph.add_edge("hook", "script")
    graph.add_edge("script", "script_qa")
    graph.add_edge("script_qa", "voice")
    graph.add_edge("voice", "background")
    graph.add_edge("background", "story_card")
    graph.add_edge("story_card", "assemble")
    graph.add_edge("assemble", "metadata")
    graph.add_edge("metadata", "compliance")
    graph.add_edge("compliance", "publish")
    graph.add_edge("publish", END)

    return graph.compile()


# Compiled once at import time — stateless graph, safe to share across runs.
pipeline = build_pipeline()
