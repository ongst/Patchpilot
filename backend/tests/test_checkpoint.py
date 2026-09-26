import sqlite3
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ApprovalState(TypedDict, total=False):
    patch: str
    approved: bool


def build_graph(connection: sqlite3.Connection):
    def approval(state: ApprovalState):
        answer = interrupt({"stage": "apply_patch", "patch": state["patch"]})
        return {"approved": bool(answer["approved"])}

    graph = StateGraph(ApprovalState)
    graph.add_node("approval", approval)
    graph.add_edge(START, "approval")
    graph.add_edge("approval", END)
    return graph.compile(checkpointer=SqliteSaver(connection))


def test_approval_can_resume_after_connection_restart(tmp_path: Path):
    checkpoint = tmp_path / "checkpoint.sqlite3"
    config = {"configurable": {"thread_id": "resume-test"}}

    first_connection = sqlite3.connect(checkpoint, check_same_thread=False)
    first_graph = build_graph(first_connection)
    paused = first_graph.invoke({"patch": "diff --git ..."}, config=config)
    assert paused["__interrupt__"]
    first_connection.close()

    second_connection = sqlite3.connect(checkpoint, check_same_thread=False)
    second_graph = build_graph(second_connection)
    resumed = second_graph.invoke(Command(resume={"approved": True}), config=config)
    assert resumed["approved"] is True
    second_connection.close()
