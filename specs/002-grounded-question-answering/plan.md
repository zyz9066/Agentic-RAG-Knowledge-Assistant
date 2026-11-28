# Implementation Plan: Evidence-Grounded Question Answering

**Branch**: `002-grounded-question-answering` | **Date**: 2026-11-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature 002 specification and the [project constitution](../../.specify/memory/constitution.md).

## Summary

Add a distinct Ask Questions view over the existing committed knowledge base.
A bounded CrewAI Flow performs deterministic retrieval and runs separate
local-model drafting and verification tasks. A claim is supported only when
its cited evidence directly states it; faithful paraphrase is allowed, but
cross-passage inference is not, and unresolved contradictions are
indeterminate. The application validates citations and source versions before
rendering supported claims, partial answers, abstention, or safe failures.
Every question receives a non-persisted, content-free trace; Langfuse export
remains availability- and authorization-gated. Contentful evaluation fields
also require per-run confirmation and verified non-sensitive sources.

## Technical Context

**Language/Version**: Python 3.11-3.13; retain the existing CI matrix.

**Primary Dependencies**: Streamlit 1.67.0, FastEmbed 0.9.1, Langfuse 5.2.0,
SQLite, pypdf; plan to lock CrewAI 1.15.45 after compatibility validation.
Manually installed Ollama and a manually prepared `qwen2.5:7b` model are
runtime prerequisites, not application-managed downloads.

**Storage**: Existing local SQLite database, with a transactional document
revision migration. No persistent question history or additional vector store.

**Testing**: pytest with deterministic local substitutes, network denial,
Ruff, Pyright, Streamlit AppTest and browser checks; local-model evaluation
and live Langfuse checks opt-in.

**Target Platform**: Windows and Linux; local, loopback-bound Streamlit app.

**Project Type**: Small Python modular monolith.

**Performance Goals**: No latency or accuracy target is asserted. Enforce
120 seconds per model call, 300 seconds per worker, at most one retry per task,
8,192 input tokens, and 1,024 generated output tokens. These are execution
ceilings, not latency guarantees.

**Constraints**: Local inference only; no answer-model downloads, external
model fallback, automatic content capture, persistent conversation history,
or unapproved trace delivery. Input tokens include instructions, question,
and evidence; overflow fails without truncating supporting evidence. Each
session has at most one active question. Freshness checks run before
publication and on reruns or state-changing actions (input edits, submission,
navigation, keyboard/pointer activation), not passive focus, hover, or scroll.
Checks are point-in-time; idle views can be stale.

**Scale/Scope**: Single-user local deployment and a small evaluation corpus;
no authentication, multi-user access, or throughput guarantee.

## Constitution Check

| Principle | Pre-design and post-design assessment |
|-----------|----------------------------------------|
| I. Evidence and provenance | PASS: claims are verified against their own citations; only direct statements or faithful paraphrases are supported, unresolved contradictions are indeterminate, and source identity/content is rechecked. This conservative rule still permits multiple independently supported claims in a multi-source answer. |
| II. Security and privacy | PASS by design: boundary validation, untrusted evidence, least-capability agents, a local-only controlled runtime, sanitized errors, content-free non-persisted local traces, and a per-run confirmation plus destination authorization for contentful evaluation export. Runtime egress and exporter controls remain verification gates. |
| III. Modular Python architecture | PASS: deterministic retrieval, version validation, trace permission and rendering stay in application code; CrewAI orchestrates bounded drafting and checking. |
| IV. Verifiable quality | PASS: offline fakes cover core logic; local-model evaluation and live tracing are opt-in and measured honestly. |
| V. Observability and reliability | PASS by design: every request creates a content-free, non-persisted trace of entered workflow stages; Langfuse exports only when available and authorized, and export failures remain separate from answer outcomes. Confirmation signals must be verified without treating flush as delivery proof. |
| Technical/workflow constraints | PASS by design: Python floor, locked dependencies, typed interfaces, Ruff, Streamlit, SQLite, CrewAI, Langfuse, Spec Kit and CI are retained. The dependency/runtime matrix remains unverified until implementation. |

No exception is proposed. A failed runtime privacy, matrix, freshness, or trace
test is a release blocker, not an accepted constitution exception.

**Requirements readiness**: The clarifications in `spec.md` and
`contracts/question-workflow.md` define error guidance, trace-delivery
confirmation, and element-specific accessibility. The reviewer-owned
`checklists/question-readiness.md` has been reconciled against those
definitions, with all 40 criteria checked for the current design. Checkbox
state represents requirements review, not completed implementation; repeat
the review if later changes affect a criterion. T002 in `tasks.md` is the
pre-implementation process gate for confirming this alignment, not a product
requirement.

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
├── local_model.py        # guarded Ollama adapter
├── question_jobs.py      # atomic per-session job ownership
├── question_errors.py    # safe user guidance by error code
└── question_workflow.py  # flow, structured outcomes, citation validation
tests/
├── conftest.py
├── crewai_test_support.py
├── unit/                 # deterministic guards, claim rules, and flow
└── integration/          # storage races, AppTest/browser, offline and opt-in checks
evaluation/feature_002/   # redistributable sources and case dataset
scripts/evaluate_feature_002.py # explicit opt-in local-model evaluator
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
   classify each claim against its cited evidence. A claim is supported only
   when its cited passages directly state it; faithful paraphrase is allowed,
   cross-passage inference is not, and unresolved contradiction is
   indeterminate. Enforce complete structured outcomes, explicit agent LLMs,
   the FR-005 call/worker/retry/token ceilings, and no tools or memory.
   Application code validates citation membership and support outcomes.
   A failed task, malformed output, or deadline is an error; an indeterminate
   claim is omitted, not a workflow error.
4. **Local runtime**: Supervise one configured local Ollama instance using a
   manually installed executable, cloud disabled, a literal loopback endpoint,
   and a locally present model. Route through a controlled adapter with peer,
   proxy, redirect and remote-model checks. Enforce 120-second call and
   300-second worker deadlines, at most one retry per task, 8,192 input tokens,
   and 1,024 output tokens. Bound requests and worker lifetime;
   never download a model or fall back. The operator must trust the runtime
   and its local environment. See [research.md](research.md).
5. **Session and publication**: An atomic session-owned job registry prevents
   overlap across reruns; the worker cannot mutate Streamlit state. The UI
   observes progress and accepts only the matching active request's terminal
   result. Before publication and on each subsequent rerun or state-changing
   action (input edits, submission, navigation, keyboard/pointer activation),
   recheck cited revisions and content in one short committed read. Passive
   focus, hover, and scrolling do not trigger checks. Remove affected claims
   and warn. Disclose the idle-view and post-check race.
6. **Observability and evaluation**: Create a content-free, non-persisted
   trace record for every question, including when Langfuse export is disabled
   or unavailable. Attempt Langfuse export only when available and authorized.
   A selected evaluation request must also receive a separate per-run
   confirmation for the disclosed question and source IDs. Serialize
   destination authorization and full-content source eligibility checks with
   dispatch. Create original evaluation sources/cases and an opt-in evaluator
   that emits per-case observations without generating the final evaluation
   report.
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
  proof of delivery; mark a trace confirmed only on an explicit server
  acknowledgment tied to it, and otherwise preserve `unconfirmed`.
- Verify labeled controls, keyboard operation and visible focus, screen-reader
  announcements for progress/status/errors, readable source references, and
  warnings that do not rely on color alone. Record limitations without
  claiming formal WCAG certification.
- Verify the evaluator emits one structured JSONL observation per case using
  the workflow-contract schema and allowed review-status values. Human
  reviewers update a local copy; pending and unavailable remain distinct from
  negative outcomes, and no review result or metric is fabricated.
- Verify that every request creates a transient content-free trace; ordinary
  and Feature 001 exports remain content-free. For evaluation fields, test
  selection, separate per-run confirmation, destination authorization, source
  eligibility, and revocation as independent gates.
- Evaluate local-model answers against the case dataset with the opt-in
  evaluator; record expected-point coverage, every displayed claim and cited
  source correctness, abstention quality, missing points, relevant failures,
  and timing only when measured. Do not generate the final evaluation report
  or claim unmeasured quality.
- Reopen the question-readiness review if implementation planning changes any
  checked criterion; checklist state is a requirements gate, not evidence that
  implementation or verification is complete.

## Complexity Tracking

No constitutional exception or additional project/service is proposed.
