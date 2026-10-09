# Tests

Warding uses pytest with pytest-asyncio for async tests.

## Running Tests

```bash
# Full gate (see AGENTS.md "The gate before you commit"):
python3 scripts/check_black_formatting.py && python3 scripts/check_subprocess_encoding.py && isort src/warding test
flake8 src/warding test && mypy src/warding
python -m pytest

# Fast iteration — only tests affected by changes:
python -m pytest --testmon --override-ini="addopts=-v --durations=5 --color=yes" -q

# Specific test file:
python -m pytest test/test_dashboard_chat.py --override-ini="addopts=-v --durations=5 --color=yes" -q

# Specific test by keyword:
python -m pytest -k "test_warm_pool" --override-ini="addopts=-v --durations=5 --color=yes" -q

# Only previously failed:
python -m pytest --lf --override-ini="addopts=-v --durations=5 --color=yes" -q
```

The `--override-ini` flag skips coverage measurement (configured in `setup.cfg`) for faster iteration.

## Test Directories

- `test/` — main test directory
- `tests/` — additional tests

## Conventions

- Test files: `test/test_<module>.py`
- Use `pytest-asyncio` with `mode=strict` — every async test needs `@pytest.mark.asyncio`
- Use `tmp_path` fixture for filesystem tests
- Use `monkeypatch` for config overrides
- Mock external processes (kiro-cli) — never spawn real processes in tests
- Group related tests in classes: `class TestFeatureName:`

## Smoke Tests

- `test/smoke_gateway.sh` — end-to-end gateway smoke test
- `test/smoke_sandbox.sh` — sandbox isolation smoke test
