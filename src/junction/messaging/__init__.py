"""Messaging transport abstraction (`junction.messaging`).

Channel-neutral contracts shared by Slack and future messaging channels.
This package depends on nothing in ``junction.slack`` / ``junction.dashboard``;
both depend on ``junction.messaging``, never the reverse.
"""

from __future__ import annotations

from junction.messaging.approval import (
    APPROVAL_TIMEOUT_S,
    PendingApprovals,
    SessionApprovalDecider,
)
from junction.messaging.driver import (
    APPROVAL_AUTO,
    APPROVAL_INTERACTIVE,
    APPROVAL_TRUST,
    APPROVAL_TRUST_READS,
    TurnDriver,
)
from junction.messaging.link import (
    SLACK_NAMESPACE,
    ChannelLink,
    canonical_key,
    is_legacy_slack_key,
    legacy_key,
    session_key,
)
from junction.messaging.renderer import (
    COMPACTION,
    DONE,
    OUTPUT_KINDS,
    PROMPT_CHOICE,
    STEER_CONSUMED,
    TEXT_CHUNK,
    THINKING,
    TOOL_CALL,
    OutputEvent,
    Renderer,
    chunk_text,
)
from junction.messaging.transport import (
    ConfiguredChannelTarget,
    InboundMessage,
    MessagingTransport,
    TransportCapabilities,
)

__all__ = [
    # Layer 1
    "MessagingTransport",
    "TransportCapabilities",
    "InboundMessage",
    "ConfiguredChannelTarget",
    # Layer 2
    "Renderer",
    "OutputEvent",
    "chunk_text",
    "OUTPUT_KINDS",
    "TEXT_CHUNK",
    "THINKING",
    "TOOL_CALL",
    "PROMPT_CHOICE",
    "COMPACTION",
    "DONE",
    "STEER_CONSUMED",
    # Layer 2 driver
    "TurnDriver",
    "APPROVAL_AUTO",
    "APPROVAL_TRUST",
    "APPROVAL_TRUST_READS",
    "APPROVAL_INTERACTIVE",
    # Layer 2 approvals
    "PendingApprovals",
    "SessionApprovalDecider",
    "APPROVAL_TIMEOUT_S",
    # Layer 3
    "ChannelLink",
    "session_key",
    "canonical_key",
    "legacy_key",
    "is_legacy_slack_key",
    "SLACK_NAMESPACE",
]
