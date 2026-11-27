# Quickstart and Validation: Evidence-Grounded Question Answering

This is a plan for use **after Feature 002 is implemented**. It is not evidence
that these scenarios or the local answer model have already passed.

## Prerequisites and setup

1. Use Windows or Linux with Python 3.11-3.13 and `uv`. After the feature's
   dependency and lockfile changes are committed, from the repository root run:

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
3. Ensure the application-owned Ollama instance is started with cloud features
   disabled (`OLLAMA_NO_CLOUD=1`), listens only on its configured literal
   loopback address, and uses the prepared local model. Do not direct it through
   a proxy, tunnel, remote model or externally managed forwarding service.
   Prevent a port conflict with any separately running Ollama service. The
   runtime and machine are operator-trusted; a loopback address alone cannot
   establish that an arbitrary service will not forward content.
4. Prepare the existing FastEmbed cache if running offline; Feature 001 may
   otherwise download its embedding model on first use. Configure the local
   knowledge directory as documented in the [project README](../../README.md).
   Langfuse credentials are optional and must remain outside source control.

## Offline automated checks

After implementation, run from the repository root:

```powershell
uv run --locked ruff check app tests
uv run --locked ruff format --check app tests
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

## Manual question and source-change checks

1. Start `.\run.ps1`; confirm the UI is loopback-only. Index the feature's
   bundled non-sensitive evaluation documents through the existing upload
   view. Open Ask Questions.
2. Submit an answerable example. Observe textual progress, supported claims,
   exact source filename and chunk ID. Submit a multi-source example and
   inspect each source. Submit an unanswerable example and expect uncertainty
   or abstention, not a fabricated answer.
3. Submit blank text and confirm no workflow starts. Test an empty knowledge
   base separately and expect a no-knowledge message, not a model failure.
   Submit while a question is active and expect a wait message without a
   second job. Rerun or navigate without submitting and confirm no new job.
4. Replace a cited filename with different content while a question is
   processing, and again after an answer appears. At the before-publication
   or next interaction check, the affected claim must disappear, a warning
   must request resubmission, and unaffected supported claims may remain.
   Repeat with identical-content replacement and with a simulated failed
   replacement. An idle view can be stale; its disclosure must say so.
5. Test a document containing an instruction to disregard answering rules,
   fabricated and non-supporting citations, and indeterminate support.
   Deterministic tests must reject these supplied cases; any real-model
   results are observations, not proof of immunity.
6. Exercise unavailable model, invalid model configuration, retrieval failure
   and an execution deadline. Expect distinct safe actionable errors, no
   automatic download, and no success-shaped response. Verify keyboard
   navigation, textual progress and source references in the browser; record
   whether a real screen reader was actually used.

## Trace privacy and optional live checks

1. With tracing absent or disabled, verify the question outcome remains
   unchanged and an appropriate separate diagnostic or permission state
   appears. Use recording sinks and transport failures to check payloads and
   revocation offline.
2. To inspect live Langfuse, opt in explicitly using only non-sensitive
   material and follow the existing destination authorization or local
   confirmation workflow. Ordinary question traces must not contain the
   question, filenames, chunk IDs or document text. Check meaningful entered
   steps, status and latency; model/usage appear only if available.
3. Select a bundled evaluation case only after reviewing the disclosed
   question, destination and fields. With independent destination permission,
   inspect whether its question and only verified sample-source identifiers
   appear. Same-name different-content, unrelated, and unverifiable sources
   must be omitted. Revocation prevents new dispatch; already dispatched data
   cannot be recalled. Do not infer confirmed delivery from a flush alone.
4. Run the implemented opt-in local-model evaluation against the bundled cases
   and record individual observed answer points, citation correctness,
   abstentions, failures and any measured timing. Human-review actual results;
   mark unrun checks and unavailable metrics as such. Generating the final
   evaluation report is a separate, explicitly requested action.

See the [workflow contract](contracts/question-workflow.md),
[data model](data-model.md), and [research](research.md) for precise
consistency, runtime, privacy and verification requirements.
