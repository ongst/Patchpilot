import pytest
from patchpilot.models import RunCreate
from pydantic import ValidationError


def test_run_create_validates_issue_and_repo():
    run = RunCreate(
        repo_url="https://github.com/example/demo",
        issue_text="The add function subtracts its arguments",
    )
    assert str(run.repo_url).startswith("https://github.com/")
    with pytest.raises(ValidationError):
        RunCreate(repo_url="https://example.com/demo", issue_text="long enough issue")
