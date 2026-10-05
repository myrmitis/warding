"""A successful short answer is not an exception from the harness."""

from __future__ import annotations

import pytest

from junction.harness_router import limits


@pytest.mark.parametrize(
    "reply",
    [
        "Run codex login",
        "Run `codex login`",
        "Run opencode auth login",
        "Please run codex login to authenticate.",
        "To authenticate Codex, run codex login.",
        "The daily limit resets at midnight.",
        "Daily limit means requests per day.",
        "Weekly limit is a plan setting.",
        "Upgrade to Pro for a higher daily limit.",
        "I added a rate limiter to the API.",
        "Rate limit exceeded, please retry",
        "Authentication required means you must sign in.",
        "Not logged in users should see the sign-in page.",
        "Invalid API key errors are handled by the client.",
        "Usage limit reached is the error we catch.",
        "Insufficient credits are reported by OpenRouter.",
        "You've reached your speed limit.",
        'The harness printed "You\'ve hit your usage limit."',
        "`Authentication required` is the message to display.",
        "```text\nYou've hit your usage limit.\n```",
        "Please run /login first to test the sign-in flow.",
        "",
        "   ",
    ],
)
def test_short_answers_do_not_rest_a_lane(reply: str) -> None:
    assert limits.limit_notice_failure(reply) == ""


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("You've hit your usage limit.", limits.FAILURE_USAGE_LIMIT),
        ("You’ve hit your usage limit.", limits.FAILURE_USAGE_LIMIT),
        ("You have reached your weekly usage limit.", limits.FAILURE_USAGE_LIMIT),
        (
            "You've hit your usage limit. Upgrade to Pro or try again in 2 hours 5 minutes.",
            limits.FAILURE_USAGE_LIMIT,
        ),
        ("Claude AI usage limit reached|1800003600", limits.FAILURE_USAGE_LIMIT),
        ("5-hour limit reached ∙ resets 3pm", limits.FAILURE_USAGE_LIMIT),
        ("Daily limit reached. Try again tomorrow.", limits.FAILURE_USAGE_LIMIT),
        ("Monthly limit exceeded", limits.FAILURE_USAGE_LIMIT),
        ("Quota exhausted", limits.FAILURE_USAGE_LIMIT),
        ("Insufficient credits. Add more at openrouter.ai", limits.FAILURE_USAGE_LIMIT),
        ("  USAGE LIMIT REACHED  ", limits.FAILURE_USAGE_LIMIT),
        ("Not logged in. Run codex login", limits.FAILURE_AUTH),
        ("Authentication required", limits.FAILURE_AUTH),
        ("Invalid API key · Please run /login", limits.FAILURE_AUTH),
        ("API key is missing", limits.FAILURE_AUTH),
        ("Please run /login first", limits.FAILURE_AUTH),
        ("Login expired. Please sign in again.", limits.FAILURE_AUTH),
    ],
)
def test_recognizable_harness_notices_still_rest_a_lane(reply: str, expected: str) -> None:
    assert limits.limit_notice_failure(reply) == expected


def test_exception_classification_stays_broader_than_successful_output() -> None:
    for text, expected in (
        ("Run codex login", limits.FAILURE_AUTH),
        ("daily limit", limits.FAILURE_USAGE_LIMIT),
        ("HTTP 429 Too Many Requests", limits.FAILURE_RATE_LIMIT),
    ):
        assert limits.classify_failure(text) == expected
        assert limits.classify_exception(RuntimeError(text)) == expected
        assert limits.limit_notice_failure(text) == ""


def test_long_reply_with_notice_prefix_is_still_an_answer() -> None:
    reply = "You've hit your usage limit. " + "x" * limits.LIMIT_NOTICE_MAX_CHARS
    assert limits.limit_notice_failure(reply) == ""
