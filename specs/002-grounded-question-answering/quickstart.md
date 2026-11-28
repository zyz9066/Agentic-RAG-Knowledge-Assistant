# Quickstart and Validation: Evidence-Grounded Question Answering

This quickstart describes current Feature 002 setup and verification. It does
not claim a live model, Langfuse service, browser accessibility audit, or
cross-platform CI matrix has passed.

## Prerequisites and setup

1. Use Windows or Linux with Python 3.11-3.13 and `uv`. From the repository
   root run:

   ```powershell
   uv sync --locked --all-groups
   ```

2. Install a trusted [Ollama runtime](https://ollama.com/download) manually
   and prepare its local model separately. For the planned baseline, with the
   Ollama service running for this explicit one-time preparation:

   ```powershell
   ollama pull qwen2.5:7b
   ollama list
   ```

   The pull downloads model files and needs network access; it does not require
   sending a question or document. The application must never pull a model.
   The catalog lists roughly 4.7 GB for the 7B model; allow additional disk,
   RAM or VRAM for runtime, context, embeddings and the OS. Actual memory and
   latency depend on hardware and context and are not yet measured. Follow
   implementation documentation for executable and cache configuration.
3. Configure `ANSWER_MODEL`, `OLLAMA_HOST`, and `OLLAMA_EXECUTABLE` through
   environment variables (see the [example configuration](../../.env.example)).
   The application starts its own `ollama serve` process when a question is
   submitted and indexed documents exist. It sets `OLLAMA_NO_CLOUD=1`, removes
   proxy variables from the child environment, validates the direct loopback
   peer, refuses an occupied port, and stops its owned process when Streamlit
   exits. Do not use a remote model, proxy, tunnel, or externally managed
   forwarding service. A loopback address alone cannot establish that an
   arbitrary pre-existing service will not forward content.
4. Prepare the existing FastEmbed cache if running offline; Feature 001 may
   otherwise download its embedding model on first use. Configure the local
   knowledge directory as documented in the [project README](../../README.md).
   Langfuse credentials are optional and must remain outside source control.

## Offline automated checks

After implementation, run from the repository root:

```powershell
uv run --locked ruff check app tests scripts
uv run --locked ruff format --check app tests scripts
uv run --locked pyright
uv run --locked pytest
```

Default tests must use deterministic embedding, CrewAI model, storage/trace
substitutes where appropriate and reject unexpected network access. Verify
the full Windows/Linux Python 3.11-3.13 CI matrix separately. Tests must
cover source replacement and migration, privacy and trace isolation,
claims/citations, abstention, prompt injection fixtures, worker limits,
overlapping submission and UI reruns. No real model, live Langfuse or model
download is required for the default suite.

### Observed verification

On Windows with Python 3.13.18, the latest offline run reported **140 passed
and 3 skipped**. The three skips were opt-in credentialed model/trace checks.
Ruff lint, Ruff formatting, Pyright, the evaluator module's `--help` command,
and `git diff --check` all passed. Live model/Langfuse checks, manual
keyboard/screen-reader checks, and the Linux/Python 3.11-3.13 CI matrix were
not run; no result is claimed for them.

## Manual question and source-change checks

1. Start `.\run.ps1`; confirm the UI is loopback-only. Index the feature's
   bundled non-sensitive evaluation documents through the existing upload
   view. Open Ask Questions.
2. Submit an answerable example. Observe textual progress, supported claims,
   exact source filename and chunk ID. Submit the multi-source example and
   verify it returns at least two distinct facts, each directly supported by
   its own source, without deriving a claim across sources. Submit an
   unanswerable example and expect uncertainty or abstention, not a fabricated
   answer.
3. Submit blank text and confirm no workflow starts. Test an empty knowledge
   base separately and expect a no-knowledge message, not a model failure.
   Submit while a question is active and expect a wait message without a
   second job. Rerun or navigate without submitting and confirm no new job.
4. Replace a cited filename with different content while a question is
   processing, and again after an answer appears. At the before-publication
   check, every app rerun, and each state-changing action (question edit,
   submission, navigation, keyboard/pointer activation), the affected claim
   must disappear, a warning must request resubmission, and unaffected
   supported claims may remain. Passive focus, hover, and scrolling do not
   trigger checks. Repeat with identical-content replacement and with a
   simulated failed replacement. An idle view can be stale; its disclosure
   must say so.
5. Test a document containing an instruction to disregard answering rules,
   fabricated and non-supporting citations, and indeterminate support.
   Deterministic tests must reject these supplied cases; any real-model
   results are observations, not proof of immunity.
6. Exercise unavailable model, invalid model configuration, retrieval failure
   and an execution deadline. Expect category-specific safe guidance: manual
   model setup, documented index recovery, retry with less evidence or after
   service recovery, or retry/contact-maintainer guidance with only an opaque
   operation ID for repeated task/model failures. Verify tracing failures are
   reported separately. Confirm there is no automatic download or
   success-shaped response.
7. Verify the input, submit, and trace-disclosure controls have programmatic
   labels, keyboard operation, and visible focus. Use a screen reader to check
   progress/status/error announcements and readable source references; verify
   warnings do not rely on color alone. Record observed limitations; do not
   claim formal WCAG certification.

## Trace privacy and optional live checks

1. With tracing absent or disabled, verify the question outcome remains
   unchanged and an appropriate separate diagnostic or permission state
   appears. Use recording sinks and transport failures to check payloads and
   revocation offline.
2. To inspect live Langfuse, run the explicitly opt-in synthetic smoke check
   below or use non-sensitive material and follow the existing destination
   authorization or local confirmation workflow. Ordinary question traces must not contain the
   question, filenames, chunk IDs or document text. Check meaningful entered
   steps, status and latency; model/usage appear only if available.
3. Select a bundled evaluation case only after reviewing the disclosed
   question, destination and fields, then separately confirm those contentful
   fields for that run. With independent destination permission, inspect
   whether its question and only verified sample-source identifiers appear.
   Same-name different-content, unrelated, and unverifiable sources must be
   omitted. Revocation prevents new dispatch; already dispatched data cannot
   be recalled. A trace is confirmed only when an explicit server
   acknowledgment is tied to it. Queueing or flushing without that
   acknowledgment remains unconfirmed; test and report disabled, unavailable,
   failed, unconfirmed, and confirmed states separately.
4. Run the implemented opt-in local-model evaluation against the bundled cases:

   ```powershell
   uv run --locked python -m scripts.evaluate_feature_002 --dataset evaluation\feature_002\cases.jsonl --confirm-local-model
   ```

   The command must use the local model and emit one JSONL object per case
   without generating the final evaluation report. Each object includes case
   ID, workflow status, expected sources, expected-point review entries, and
   each displayed claim with cited filename/chunk IDs and support/citation
   review statuses. Expected-point status is `pending`, `covered`,
   `not_covered`, or `unavailable`; claim-support status is `pending`,
   `supported`, `unsupported`, `indeterminate`, or `unavailable`; citation
   status is `pending`, `correct`, `incorrect`, or `unavailable`.
   `abstention_review` is `pending`, `appropriate`, `inappropriate`,
   `not_applicable`, or `unavailable`. `missing_points_review` has status
   `pending`, `reviewed`, or `unavailable`; its point list is null until
   reviewed, and an empty list means no points were missed. The object also
   has a safe failure code or null and measured elapsed time or null.
   Redirect output to a local file if you want to retain it, then have a human
   reviewer update the pending fields; unavailable is not a negative result.
   The evaluator must not invent review results or aggregate metrics. The
   final evaluation report is a separate, explicitly requested action.

See the [workflow contract](contracts/question-workflow.md),
[data model](data-model.md), and [research](research.md) for precise
consistency, runtime, privacy and verification requirements.

## Explicitly opt-in smoke checks

The local model smoke check uses only the bundled orchard source and requires
the manually prepared model:

```powershell
$env:RUN_QUESTION_MODEL_TESTS = "1"
uv run --locked pytest tests\integration\test_real_question_model.py
```

The Langfuse smoke check sends a synthetic trace containing only an opaque
operation ID, an allowlisted step, status, and duration. It requires valid
credentials and the external-destination authorization flag below. A
successful SDK flush remains `unconfirmed` unless the integration exposes an
explicit server acknowledgment:

```powershell
$env:RUN_LANGFUSE_QUESTION_TESTS = "1"
uv run --locked pytest tests\integration\test_live_question_trace.py
```
