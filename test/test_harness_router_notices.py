"""A successful short answer is not an exception from the harness."""

from __future__ import annotations

import json

import pytest

from warding.harness_router import limits


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


_CODEX_400 = (
    '{"type":"error","status":400,"error":{"type":"invalid_request_error",'
    '"message":"The \'gpt-6.1-sol\' model is not supported when using Codex with a ChatGPT account."}}'
)
_CODEX_429 = "exceeded retry limit, last status: 429 Too Many Requests"


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (_CODEX_400, limits.FAILURE_OTHER),
        (_CODEX_429, limits.FAILURE_RATE_LIMIT),
        ("  " + _CODEX_429.upper() + "\n", limits.FAILURE_RATE_LIMIT),
        ("exceeded retry limit, last status: 400 Bad Request", limits.FAILURE_OTHER),
        (
            '{"type":"error","status":429,"error":{"type":"rate_limit_error",'
            '"message":"Too many requests"}}',
            limits.FAILURE_RATE_LIMIT,
        ),
        (
            '{"type":"error","status":429,"error":{"type":"insufficient_quota",'
            '"message":"Quota exhausted"}}',
            limits.FAILURE_USAGE_LIMIT,
        ),
        (
            '{"type":"error","status":401,"error":{"type":"authentication_error",'
            '"message":"Invalid API key"}}',
            limits.FAILURE_AUTH,
        ),
        (
            '{"type":"error","status":400,"error":{"type":"invalid_request_error",'
            '"message":"The HTTP 429 quota example is invalid"}}',
            limits.FAILURE_OTHER,
        ),
    ],
)
def test_codex_provider_errors_are_failures(reply: str, expected: str) -> None:
    assert limits.limit_notice_failure(reply, harness="codex") == expected
    # A typed failure's class wins over incidental words in its error detail.
    assert limits.classify_exception(limits.HarnessLaneFailure(expected, reply)) == expected


@pytest.mark.parametrize(
    "reply",
    [
        "HTTP 429 Too Many Requests",
        "Rate limit exceeded, please retry",
        "I fixed an unsupported model error (HTTP 400).",
        "The provider returned " + _CODEX_429,
        _CODEX_429 + " means the client should back off.",
        "`" + _CODEX_429 + "`",
        "```json\n" + _CODEX_400 + "\n```",
        "Example: " + _CODEX_400,
        _CODEX_400 + "\nUse a supported model instead.",
        _CODEX_400[:-1],
        '["error", 429]',
        '{"type":"error","status":200,"error":{"type":"x","message":"ok"}}',
        '{"type":"error","status":"429","error":{"type":"x","message":"failed"}}',
        '{"type":"error","status":429,"error":"Too many requests"}',
        '{"type":"error","status":429,"error":{"message":"failed"}}',
        '{"type":"error","status":429,"error":{"type":"x","message":null}}',
    ],
)
def test_codex_answers_and_malformed_envelopes_remain_answers(reply: str) -> None:
    assert limits.limit_notice_failure(reply, harness="codex") == ""


@pytest.mark.parametrize("harness", ["", "claude", "kiro", "opencode", "cursor"])
@pytest.mark.parametrize("reply", [_CODEX_400, _CODEX_429])
def test_codex_signatures_do_not_change_other_harnesses(harness: str, reply: str) -> None:
    assert limits.limit_notice_failure(reply, harness=harness) == ""


def test_long_codex_provider_error_is_not_inferred_from_output() -> None:
    reply = json.dumps(
        {"type": "error", "status": 429, "error": {"type": "x", "message": "x" * 400}}
    )
    assert len(reply) > limits.LIMIT_NOTICE_MAX_CHARS
    assert limits.limit_notice_failure(reply, harness="codex") == ""


@pytest.mark.parametrize(
    ("reply", "failure", "rest"),
    [
        (_CODEX_429, limits.FAILURE_RATE_LIMIT, 120),
        (_CODEX_400, limits.FAILURE_OTHER, 0),
    ],
)
def test_codex_provider_errors_use_their_own_cooldown_and_failure_counters(
    tmp_path, reply: str, failure: str, rest: int
) -> None:
    from warding.harness_router.ledger import UsageLedger

    ledger = UsageLedger(tmp_path)
    moment = 1_800_000_000.0
    older = ledger.record_dispatch("codex", now=moment)
    detected = limits.limit_notice_failure(reply, harness="codex")
    assert detected == failure
    assert limits.cooldown_seconds(detected, reply) == rest
    deadline = ledger.record_outcome(
        "codex", ok=False, failure=detected, text=reply, harness="codex", now=moment
    )
    assert deadline == (moment + rest if rest else 0)
    usage = ledger.snapshot()["codex"]
    assert (usage.ok, usage.failed, usage.limited) == (0, 1, int(bool(rest)))
    if rest:
        ledger.record_outcome("codex", ok=True, dispatch_seq=older, now=moment)
        assert ledger.snapshot()["codex"].cooldown_until == deadline
