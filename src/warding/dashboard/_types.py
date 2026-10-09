"""Shared TYPE_CHECKING imports for dashboard modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warding.context import ContextBuilder
    from warding.cron import CronService
    from warding.history import ConversationLog, HistoryConsolidator
    from warding.learn import LessonStore
    from warding.session import SessionManager
    from warding.subagent import SubagentManager
    from warding.taskrunner import TaskRunner

__all__ = [
    "ContextBuilder",
    "CronService",
    "ConversationLog",
    "HistoryConsolidator",
    "LessonStore",
    "SessionManager",
    "SubagentManager",
    "TaskRunner",
]
