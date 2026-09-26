from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from patchpilot.config import Settings
from patchpilot.models import RepairPlan, TestResult
from patchpilot.repo_tools import RepositoryTools


class RepairProposal(BaseModel):
    plan: RepairPlan
    patch: str = Field(min_length=20)


@dataclass(frozen=True)
class ProposalResult:
    proposal: RepairProposal
    inspected_files: list[str]
    token_usage: int


SYSTEM_PROMPT = """You are PatchPilot, a careful code repair agent.
You may only inspect the repository through the provided read-only tools. Never invent file contents.
First inspect the project and relevant tests. Then return one JSON object with exactly these keys:
{
  "plan": {
    "summary": "short repair summary",
    "root_cause": "specific root cause",
    "steps": ["ordered implementation step"],
    "tests": ["tests to run or add"],
    "risks": ["possible regression"]
  },
  "patch": "a complete unified git diff beginning with diff --git"
}
The patch must be minimal, must not edit generated or dependency files, and must include a regression test
when practical. Do not wrap the final JSON in Markdown fences. Do not execute commands.
"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List safe repository text files, optionally filtered by a path substring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                "required": ["pattern", "limit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search repository text files for a literal query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "required": ["query", "path", "limit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a safe line range from one repository file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                "required": ["path", "start_line", "end_line"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "symbol_summary",
            "description": "Return a deterministic Python and JavaScript/TypeScript symbol map.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 500}},
                "required": ["limit"],
                "additionalProperties": False,
            },
        },
    },
]


class RepairLLM:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.llm_api_key)

    def propose(
        self,
        tools: RepositoryTools,
        issue_text: str,
        language: str,
        test_result: TestResult | None,
        current_diff: str,
        attempt: int,
    ) -> ProposalResult:
        if not self.configured:
            raise RuntimeError("PATCHPILOT_LLM_API_KEY is not configured")
        client = OpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            timeout=self.settings.llm_timeout_seconds,
        )
        failure_context = "No test result is available."
        if test_result:
            failure_context = (
                f"Test command: {test_result.command}\n"
                f"Passed: {test_result.passed}\n"
                f"Exit code: {test_result.exit_code}\n"
                f"Output:\n{test_result.output[-8000:]}"
            )
        diff_context = current_diff[-8000:] if current_diff else "<no existing changes>"
        user_prompt = f"""Repair attempt: {attempt}
Repository language: {language}
Issue:
{issue_text}

Current test information:
{failure_context}

Current uncommitted diff (a later attempt must return an incremental patch):
{diff_context}

Inspect the repository before proposing a patch.
"""
        messages: list[Any] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        total_tokens = 0

        for _ in range(self.settings.llm_max_tool_rounds):
            response = client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0,
            )
            if response.usage:
                total_tokens += response.usage.total_tokens
            message = response.choices[0].message
            messages.append(message)
            if message.tool_calls:
                for call in message.tool_calls:
                    result = self._dispatch(tools, call.function.name, call.function.arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": result,
                        }
                    )
                continue
            if not message.content:
                raise RuntimeError("Model returned neither tool calls nor a proposal")
            proposal = self._parse_proposal(message.content)
            return ProposalResult(
                proposal=proposal,
                inspected_files=sorted(tools.inspected_files),
                token_usage=total_tokens,
            )
        raise RuntimeError("Model exceeded the maximum number of tool rounds")

    def _dispatch(self, tools: RepositoryTools, name: str, raw_arguments: str) -> str:
        try:
            arguments = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object")
            if name == "list_files":
                return tools.list_files(str(arguments["pattern"]), int(arguments["limit"]))
            if name == "search_code":
                return tools.search_code(
                    str(arguments["query"]), str(arguments["path"]), int(arguments["limit"])
                )
            if name == "read_file":
                return tools.read_file(
                    str(arguments["path"]),
                    int(arguments["start_line"]),
                    int(arguments["end_line"]),
                )
            if name == "symbol_summary":
                return tools.symbol_summary(int(arguments["limit"]))
            raise ValueError(f"Unknown tool: {name}")
        except (KeyError, TypeError, ValueError) as error:
            return f"TOOL_ERROR: {error}"

    def _parse_proposal(self, content: str) -> RepairProposal:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            return RepairProposal.model_validate_json(cleaned)
        except ValidationError as error:
            raise RuntimeError(f"Model returned an invalid repair proposal: {error}") from error
