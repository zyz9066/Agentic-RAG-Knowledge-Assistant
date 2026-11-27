# Implementation Plan: Evidence-Grounded Question Answering

**Branch**: `002-grounded-question-answering` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature 002 specification and the [project constitution](../../.specify/memory/constitution.md).

## Summary

Add a distinct Ask Questions view over the existing committed knowledge base.
A bounded CrewAI Flow performs deterministic retrieval and runs separate
local-model drafting and verification tasks. The application validates
claim-associated citations, rechecks source versions, and renders only the
accepted supported claims, or explains uncertainty, abstention, or a safe
failure. Trace meaningful steps through the existing permission-controlled
Langfuse boundary. Contentful tracing is limited to explicitly selected,
verified non-sensitive evaluation cases.

## Technical Context

**Language/Version**: Python 3.11-3.13; retain the existing CI matrix.

**Primary Dependencies**: Streamlit 1.67.0, FastEmbed 0.9.1, Langfuse 5.2.0,
SQLite, pypdf; plan to lock CrewAI 1.15.45 after compatibility validation.
Manually installed Ollama and a manually prepared `qwen2.5:7b` model are
runtime prerequisites, not application-managed downloads.

**Storage**: Existing local SQLite database, with a transactional document
revision migration. No persistent question history or additional vector store.

**Testing**: pytest with deterministic local substitutes, network denial,
Ruff, Pyright, Streamlit AppTest and browser checks; local-model and live
Langfuse checks opt-in.

**Target Platform**: Windows and Linux; local, loopback-bound Streamlit app.

**Project Type**: Small Python modular monolith.

**Performance Goals**: No latency or accuracy target is asserted. Enforce
explicit limits and report actual measurements when made.

**Constraints**: Local inference only; no answer-model downloads, external
model fallback, automatic content capture, persistent conversation history,
or unapproved trace delivery. Each session has at most one active question.
Publication and rerun checks are point-in-time; idle views can be stale.

**Scale/Scope**: Single-user local deployment and a small evaluation corpus;
no authentication, multi-user access, or throughput guarantee.

## Constitution Check

| Principle | Pre-design and post-design assessment |
|-----------|----------------------------------------|
| I. Evidence and provenance | PASS: explicit claim-to-evidence verification, exact source IDs, revision/content checks, and uncertainty. Model-based semantic verification is imperfect and must be evaluated, not represented as a guarantee. |
| II. Security and privacy | PASS by design: boundary validation, untrusted evidence, least-capability agents, a local-only controlled runtime, sanitized error channels, and allowlisted authorized traces. Runtime egress and exporter controls are implementation verification gates. |
| III. Modular Python architecture | PASS: deterministic retrieval, version validation, trace permission and rendering stay in application code; CrewAI orchestrates bounded drafting and checking. |
| IV. Verifiable quality | PASS: offline fakes cover core logic; local-model evaluation and live tracing are opt-in and measured honestly. |
| V. Observability and reliability | PASS by design: entered workflow steps, status and latency are recorded without content by default; trace failures remain separate from application outcomes. SDK delivery detection must be verified. |
| Technical/workflow constraints | PASS by design: Python floor, locked dependencies, typed interfaces, Ruff, Streamlit, SQLite, CrewAI, Langfuse, Spec Kit and CI are retained. The dependency/runtime matrix remains unverified until implementation. |

No exception is proposed. A failed runtime privacy, matrix, freshness, or trace
test is a release blocker, not an accepted constitution exception.

## Project Structure

### Documentation (this feature)

```text
specs/002-grounded-question-answering/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── contracts/question-workflow.md
├── quickstart.md
├── checklists/requirements.md
└── tasks.md              # later /speckit-tasks output
```

### Source Code (repository root; proposed)

```text
app/
├── ui.py                 # separate views, session ownership, safe rendering
├── retrieval.py          # preserve public retrieval; private versioned path
├── storage.py            # revision migration and committed snapshot checks
├── ingestion.py          # existing replacement semantics remain intact
├── observability.py      # allowlisted question stages and consent checks
├── config.py             # local runtime and bounded configuration
└── question_workflow.py  # flow, structured outcomes, local model boundary
tests/
├── unit/                 # guards, source identity, privacy and flow
└── integration/          # storage races, UI, offline and opt-in checks
```

**Structure Decision**: Extend existing modules and keep the new workflow in
the current modular monolith. Split the new module only if needed for clarity.
Place original evaluation fixtures and dataset under a small repository-owned
evaluation directory during implementation. Do not change Feature 001's
public evidence shape or its upload and trace behavior.

## Architecture and sequencing

1. **Foundation and migration**: Lock compatible CrewAI dependencies; migrate
   existing document rows transactionally to opaque revisions. Mint a new
   revision in the same commit as each replacement. Preserve filename
   comparison, reservation, atomicity, model compatibility, and rollback.
2. **Versioned retrieval**: Extend the storage/retrieval seam internally so
   ranking uses the same committed snapshot as each candidate's document
   revision and chunk content. Existing `retrieve()` inputs, ranking, output,
   errors, and separate diagnostics remain unchanged. Distinguish an empty
   index from a failed lookup.
3. **CrewAI flow**: A deterministic retrieval step feeds a sequential
   two-task crew: draft atomic claims with candidate citation keys, then
   independently classify support for each claim against the referenced
   evidence. Enforce strict output validation, set agents' LLMs explicitly,
   bound iteration/retries/context/output and use no tools or memory. Validate
   citation membership and verification results outside the model. A failed
   task, malformed output, or deadline is an error; an indeterminate claim is
   omitted, not a workflow error.
4. **Local runtime**: Supervise one configured local Ollama instance using a
   manually installed executable, cloud disabled, a literal loopback endpoint,
   and a locally present model. Route through a controlled adapter with peer,
   proxy, redirect and remote-model checks. Bound requests and worker lifetime;
   never download a model or fall back. The operator must trust the runtime
   and its local environment. See [research.md](research.md).
5. **Session and publication**: An atomic session-owned job registry prevents
   overlap across reruns; the worker cannot mutate Streamlit state. The UI
   observes progress and accepts only the matching active request's terminal
   result. Before publication and on later interaction/rerun, recheck all
   citation revisions and content in one short committed read. Remove affected
   claims and warn. Explicitly disclose the idle-view and post-check race.
6. **Observability and evaluation**: Add safe, entered-stage tracing with
   separately reported export diagnostics. Reuse destination authorization
   and serialize a fresh full-content eligibility check for selected sample
   sources with dispatch. Create original evaluation documents and cases;
   test ordinary, selected, replaced and unrelated sources.
7. **Verification and documentation**: Preserve all Feature 001 tests and
   run the focused offline suite, lint, formatting and type checks, followed by
   CI matrix. Add opt-in local-model, browser accessibility and live
   Langfuse procedures. Do not claim real-model results or trace delivery
   without observing them.

Detailed interfaces and race/permission rules are in
[question-workflow.md](contracts/question-workflow.md) and
[data-model.md](data-model.md). Validation scenarios are in
[quickstart.md](quickstart.md).

## Implementation verification gates

- Verify CrewAI 1.15.45 imports, API fields, structured task behavior and
  resolution in the locked Windows/Linux Python 3.11-3.13 matrix. Prevent
  implicit converter/agent models and CrewAI's separate outbound telemetry
  or content capture; do not disable the authorized Langfuse pipeline.
- Prove by intercepted requests that only the trusted local runtime receives
  questions and evidence; reject proxy/redirect, cloud models and fallback.
  Validate the runtime's local-only and timeout behavior on both platforms.
- Prove source revision migration and retrieval are atomic, including
  identical-content replacement, rollback, concurrent replacement, before
  publication, and after display. A failed freshness read fails closed.
- Prove all relevant browser interactions, including non-form-submit edits,
  trigger a freshness check before stale claims remain visible. If native
  Streamlit events cannot satisfy this, use a minimal Streamlit v2 component
  that invalidates the displayed answer on the interaction and triggers a
  check; test keyboard and pointer paths and listener cleanup. Do not silently
  narrow the spec to form submissions.
- Verify Langfuse 5.2.0 isolation, payload allowlist, actual exporter failure
  signals and authorization/revocation races. A completed flush alone is not
  proof of delivery.
- Evaluate local-model grounding and prompt-injection cases separately from
  deterministic wiring tests; document false accepts and omissions honestly.

## Complexity Tracking

No constitutional exception or additional project/service is proposed.
