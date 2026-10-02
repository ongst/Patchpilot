import json
from pathlib import Path

import pytest
from patchpilot.config import Settings
from patchpilot.llm import RepairLLM
from patchpilot.repo_tools import RepositoryTools


def test_parse_proposal_and_tool_dispatch(tmp_path: Path):
    (tmp_path / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    llm = RepairLLM(Settings(data_dir=tmp_path / "data", workspace_dir=tmp_path / "work"))
    proposal = llm._parse_proposal(
        json.dumps(
            {
                "plan": {
                    "summary": "Fix value",
                    "root_cause": "Wrong constant",
                    "steps": ["Update return value"],
                    "tests": ["Run pytest"],
                    "risks": [],
                },
                "patch": "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n",
            }
        )
    )
    assert proposal.plan.summary == "Fix value"

    tools = RepositoryTools(tmp_path)
    output = llm._dispatch(
        tools,
        "read_file",
        json.dumps({"path": "app.py", "start_line": 1, "end_line": 2}),
    )
    assert "return 1" in output
    assert llm._dispatch(tools, "unknown", "{}").startswith("TOOL_ERROR")


def test_propose_requires_api_key(tmp_path: Path):
    llm = RepairLLM(Settings(data_dir=tmp_path / "data", workspace_dir=tmp_path / "work", llm_api_key=""))
    with pytest.raises(RuntimeError, match="API_KEY"):
        llm.propose(RepositoryTools(tmp_path), "issue", "python", None, "", 1)
