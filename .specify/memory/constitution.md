<!--
Sync Impact Report
Version change: unratified template -> 1.0.0
Modified principles: principle placeholders -> I. Evidence-Grounded Answers and Provenance;
  II. Secure Data and Privacy; III. Modular, Explicit Python Architecture;
  IV. Verifiable Quality; V. Observable, Reliable Workflows
Added sections: Technical and Security Constraints; Development and Verification Workflow
Removed sections: none
Follow-up TODOs: none
-->

# Agentic RAG Knowledge Assistant Constitution

## Core Principles

### I. Evidence-Grounded Answers and Provenance
All user-facing RAG answers MUST be grounded in retrieved evidence. The system MUST preserve
source provenance from ingestion through retrieval and generation, and MUST communicate
uncertainty or abstain when evidence is insufficient. Retrieved content MUST be treated as
untrusted data, never as instructions to override system policy. Rationale: this makes answers
auditable and limits unsupported claims and document-driven prompt injection.

### II. Secure Data and Privacy
Untrusted inputs MUST be validated at system boundaries. Agents and tools MUST receive only
the capabilities necessary for their tasks. Credentials MUST be provided through
environment-based configuration or a secret manager, never committed to source control.
Logs and telemetry MUST exclude secrets and minimize or redact personal and sensitive content.
Errors MUST be surfaced rather than silently swallowed. Rationale: documents, prompts, model
providers, and traces create data-exposure and misuse risks.

### III. Modular, Explicit Python Architecture
The application MUST remain a small modular monolith with clear UI, application/workflow,
ingestion/retrieval, persistence, configuration, and observability boundaries. Deterministic
control flow MUST remain in ordinary application code; CrewAI MUST be used where agent behavior
adds value. Agent tools, retries, and execution MUST be bounded, with explicit inputs and
expected outputs. Rationale: clear boundaries make the system easier to reason about, test,
and change without unnecessary agent complexity.

### IV. Verifiable Quality
Core behavior MUST be testable without live model-provider or observability services. Tests
SHOULD use deterministic fakes for LLM, embedding, vector-store, and Langfuse dependencies
where appropriate. Changes MUST run relevant tests, lint, and type checks before completion;
live-provider tests MUST be opt-in. Quality evaluations MUST report only measured metrics and
identify unavailable measurements. Rationale: nondeterministic model calls and external
services must not make routine verification unreliable.

### V. Observable, Reliable Workflows
Agentic and RAG workflows MUST produce traces across meaningful execution steps, including
status and latency, with model and usage metadata when available. Instrumentation MUST minimize
sensitive data, remain testable, and MUST NOT obscure application errors or break core behavior.
Rationale: traces support debugging and evaluation while preserving privacy and clear failure
behavior.

## Technical and Security Constraints

- Python 3.11 is the minimum supported version. The supported version matrix MUST be compatible
  with project dependencies and verified in CI.
- Ruff MUST be used for formatting and linting. Public interfaces MUST be typed, and
  documentation MUST remain focused and useful.
- Project dependencies MUST be declared in `pyproject.toml` and pinned reproducibly with a
  lockfile.
- Streamlit is the default lightweight UI. A feature specification MUST justify a different UI
  technology.
- Persistence MUST be accessed through small interfaces. The vector and metadata stores MUST
  suit the deployment, and data lifecycle and configuration MUST be explicit.
- CrewAI MUST orchestrate agentic workflows and Langfuse MUST provide workflow observability.
  Tests MUST be able to substitute deterministic fakes for these external behaviors.

## Development and Verification Workflow

- Feature work MUST use Spec Kit. Specifications, plans, tasks, implementation, and
  verification MUST remain aligned before work is considered complete.
- Contributors MUST run relevant tests, lint, and type checks for changes. Live-provider
  checks MUST be opt-in, and their execution instructions MUST be documented.
- Setup and operational behavior MUST be documented. Changes MUST remain focused and be
  reviewed; CI MUST run the applicable lint, type, and test checks.

## Governance

This constitution takes precedence over conflicting project practices. Feature specifications,
plans, tasks, implementation, and reviews MUST comply with it. Conflicts MUST be surfaced and
resolved before implementation. Any approved exception MUST include its rationale in the
relevant project artifact.

Amendments MUST include a rationale and an impact assessment, receive project review, and
update the version and amendment date. Versioning follows semantic versioning: MAJOR denotes
backward-incompatible principle or governance changes; MINOR denotes a new principle or section
or materially expanded guidance; PATCH denotes non-semantic clarification or editorial changes.
Feature planning and review MUST assess compliance. Automated checks MUST enforce applicable
formatting, typing, and test requirements; reviewers MUST assess the remaining principles.

**Version**: 1.0.0 | **Ratified**: 2026-11-22 | **Last Amended**: 2026-11-22
