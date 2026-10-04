"""The planner names each step's harness-router kind; nothing guesses it."""

from __future__ import annotations

import pytest

from junction.task_models import Project, Task
from junction.task_planner import parse_tasks, update_plan_tasks


def test_parse_tasks_keeps_only_known_kinds() -> None:
    tasks = parse_tasks(
        '{"steps": [{"title": "a", "kind": "Review"}, {"title": "b", "kind": "vibes"},'
        ' {"title": "c"}]}'
    )
    assert [(t.title, t.kind) for t in tasks] == [("a", "review"), ("b", ""), ("c", "")]


def test_editing_a_plan_keeps_a_kind_the_editor_did_not_send() -> None:
    run = Project(spec_path="s.md", spec_content="", status="planned")
    run.tasks = [Task(index=1, title="a", description="a", kind="test")]
    update_plan_tasks(run, [{"title": "a renamed"}])
    assert run.tasks[0].kind == "test"
    update_plan_tasks(run, [{"title": "a", "kind": "docs"}])
    assert run.tasks[0].kind == "docs"
    with pytest.raises(ValueError):
        update_plan_tasks(run, [])
