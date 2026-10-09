# Backend shard hang diagnostics

Status: diagnostic instrumentation for an intermittent worker-loss failure. Do not treat a green run as proof of a root-cause fix.

## Evidence and decision

An intermittent Python 3.12 / shard 2 hang has been seen in the backend matrix: a job lost worker `gw2` (`Not properly terminated`), continued to 99%, and was cancelled at the job limit without the normal pytest summary. The existing `--timeout=120` did not end that stall. The last printed test is not proof of the culprit in a concurrent run.

A later job on the same commit passed shard 2 and coverage upload. This establishes intermittence, not resolution. Existing evidence does not distinguish an executing test, teardown, worker transport, session finalization, or interpreter shutdown. It does not establish shard imbalance. Do not rebalance shards or retry until green on this evidence.

## What is added

`scripts/ci_pytest_diagnostics.py` is an explicitly loaded, opt-in pytest plugin. Each controller/worker process records timestamped phase transitions, node IDs, PID, and worker ID to a line-buffered JSONL journal. It emits all-thread stacks every 60 seconds and keeps observing session finalization and interpreter shutdown. The controller relays stack files to the original stderr descriptor so pytest capture cannot hide the evidence until a summary that may never appear. Worker-loss callbacks emit the worker's last journal entries; crash-item callbacks name the node without modifying reports or rescheduling tests.

The plugin does not register signals, replace pytest-timeout timers, add retries, alter test outcomes, or configure workers, splitting, scheduling, or coverage. It does not intentionally record locals or environment values. Node IDs can still contain parameter values; use the repository's normal rules against secrets in test identifiers.

The first dedicated diagnostic run was invalid as reproduction evidence because the diagnostic recorder itself was affected by a test that patches `time.time`. The recorder raised `StopIteration` after `test/test_design_tweak_devproc.py::TestStartDevProc::test_detects_listening_port`, causing a worker internal error and a secondary xdist `KeyError`. That is a defect in the first diagnostic implementation, not evidence that this application test caused the hang. The recorder is now failure-contained and has a regression probe for mocked clocks.

The validated instrumentation is loaded only in the ordinary Python 3.12 backend matrix in `.github/workflows/ci.yml`. The scheduler, shard count, `-n auto`, `--timeout=120`, coverage targets, strictness and test scope are unchanged. Each Python 3.12 shard uploads its diagnostic journal/stacks with `always()`; live console relay remains the fallback when cancellation prevents artifact upload. There is no retry-until-green path and no shard rebalancing change.

## Reproduction

From the repository root with the CI dependency set installed:

```bash
python -m pytest -p scripts.ci_pytest_diagnostics \
  --hang-diagnostics-dir="$(mktemp -d)" \
  -q -n auto --timeout=120 --splits 4 --group 2 \
  --cov=warding --cov=sage_lib
```

Keep the repository's existing pytest configuration, duration data, worker budget and strictness. Do not use a reduced suite, changed distribution, or repeated green run as evidence of resolution. Record the exact commit, Python version, run ID, job ID, attempt, outcome and coverage artifact for each reproduction.

To validate the diagnostic mechanism independently of application fixtures:

```bash
python -c 'import pytest, pytest_cov, pytest_timeout, xdist'
python -m unittest discover -s scripts -p test_ci_pytest_diagnostics.py -v
```

The import preflight makes missing xdist/timeout dependencies a CI failure rather than accepting skipped integration probes.

## Local evidence

The isolated probes cover opt-in inertness, phase journals, setup/call/teardown/session-finish stalls, interpreter thread-join stalls, console stacks visible before process exit, assertion and strict-XPASS failure preservation, and real coverage XML output. On a runtime without pytest-xdist and pytest-timeout, the two probes that need them skip; CI's import preflight turns that into a failure instead.

These are diagnostic-mechanism tests, not a full backend shard reproduction. The first remote diagnostic run exposed and failed on the instrumentation defect described above, so it is explicitly excluded as root-cause evidence. Subsequent exact-head normal-CI results are the acceptance evidence for the failure-contained instrumentation.

## Interpreting the next failure

Use the immediate `crashitem` line and worker journal for a lost worker. For a live stall, correlate the most recent phase/node ID with successive stack samples: setup/call/teardown identifies an active test; sessionfinish or interpreter-shutdown instead points to finalization. A worker-loss line without stack evidence is not enough to claim OOM or a particular exception. Preserve the first failing attempt and its artifacts before proposing a bounded reproduction/fix.

The daemon watchdog needs Python execution time; native code holding the GIL or runner termination can prevent new samples. Artifact upload is best effort at job cancellation. These limitations are not grounds to increase retries, suppress test failures, or lower coverage requirements.
