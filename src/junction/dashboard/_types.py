"""Shared TYPE_CHECKING imports for dashboard modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from junction.context import ContextBuilder
    from junction.cron import CronService
    from junction.history import ConversationLog, HistoryConsolidator
    from junction.learn import LessonStore
    from junction.session import SessionManager
    from junction.subagent import SubagentManager
    from junction.taskrunner import TaskRunner

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
