"""Tests for configurable bot_name — substitution, defaults, sanitization."""

from __future__ import annotations

from junction.config.loader import _sanitize_bot_name


class TestSanitizeBotName:
    def test_normal_name(self):
        assert _sanitize_bot_name("Alita") == "Alita"

    def test_empty_returns_empty(self):
        assert _sanitize_bot_name("") == ""

    def test_strips_braces(self):
        assert _sanitize_bot_name("{bot_name}") == "bot_name"

    def test_strips_markdown(self):
        assert _sanitize_bot_name("**Bold**") == "Bold"

    def test_max_length(self):
        assert len(_sanitize_bot_name("A" * 100)) == 50

    def test_non_string(self):
        assert _sanitize_bot_name(123) == ""  # type: ignore[arg-type]

    def test_whitespace_stripped(self):
        assert _sanitize_bot_name("  Kiro  ") == "Kiro"


class TestBotNameSubstitution:
    def test_custom_name_substituted(self):
        from junction.context import ContextBuilder

        ctx = ContextBuilder(bot_name="Alita")
        assert ctx._substitute_bot_name("You are {bot_name} 🐾") == "You are Alita 🐾"

    def test_empty_defaults_from_config(self):
        from junction.context import ContextBuilder

        # When no custom name is set, the prompt uses the product name.
        ctx = ContextBuilder(bot_name="")
        assert ctx._substitute_bot_name("You are {bot_name}.") == "You are Warding."

    def test_no_placeholder_is_noop(self):
        from junction.context import ContextBuilder

        ctx = ContextBuilder(bot_name="Alita")
        assert ctx._substitute_bot_name("No placeholder here.") == "No placeholder here."

    def test_self_referential_no_recursion(self):
        """bot_name containing {bot_name} — braces stripped by sanitizer."""
        from junction.context import ContextBuilder

        name = _sanitize_bot_name("{bot_name}")
        ctx = ContextBuilder(bot_name=name)
        assert ctx._substitute_bot_name("You are {bot_name}.") == "You are bot_name."
