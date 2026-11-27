# Research: Evidence-Grounded Question Answering

**Date**: 2026-11-26 | **Status**: Design decisions; no implementation or quality measurements

## Orchestration and verification

**Decision**: Use a short-lived CrewAI Flow to run deterministic retrieval,
then a sequential crew with a drafting task and a separate verification task.
The application, not an agent, enforces membership, output schema, source
freshness, limits, and final rendering. Inject the same explicitly configured
local-model adapter into every agent. No memory, knowledge store, delegation,
code execution, web tools, auto-instrumentation, or provider fallback.

**Rationale**: CrewAI orchestrates the required workflow without delegating
database, privacy, or publication decisions to a model. A verifier must mark
each proposed claim as supported, unsupported, or indeterminate against
specific retrieved evidence; the app retains only supported claims with
valid references. This is a risk reduction, not a proof of semantic entailment
or prompt-injection immunity. Similarity alone is never sufficient.

**Alternatives considered**: A single unverified agent cannot adequately
separate drafting from checking. A model-controlled retrieval tool could skip,
repeat, or alter retrieval; a deterministic Flow step preserves Feature 001's
retrieval contract. A rule-only entailment checker cannot generally judge
natural-language support.

**Version evidence**: CrewAI is not installed in the current environment.
PyPI's `crewai==1.15.45` metadata lists Python `>=3.10,<3.14`, consistent
with the project's Python 3.11-3.13 range. A universal 3.11-floor resolver
dry run with current direct dependencies succeeded; this is not a Windows,
Linux, or runtime compatibility test. Lock the selected version during
implementation, verify its actual fields and behavior, and run the entire
existing platform/Python matrix before claiming support. CrewAI defaults can
select an external model; never rely on defaults or conversion fallbacks.

Sources: [CrewAI package metadata](https://pypi.org/pypi/crewai/json),
[Flows](https://docs.crewai.com/en/concepts/flows),
[Tasks](https://docs.crewai.com/en/concepts/tasks),
[CrewAI 1.15.45 source](https://github.com/crewAIInc/crewAI/tree/1.15.45/lib/crewai/src/crewai).

## Local model boundary and execution

**Decision**: Target a manually installed local Ollama runtime and manually
prepared `qwen2.5:7b` as a baseline, not a quality guarantee. An application
owned instance starts with cloud features disabled and an explicit literal
loopback address. A controlled CrewAI `BaseLLM` adapter uses direct loopback
HTTP with proxies and redirects disabled, validates the connected peer and
local model metadata, and never invokes pull/create endpoints. Reject remote
model metadata, ambiguous identity, unavailable files/service, non-loopback
or unverified endpoints, and any request to fall back. Do not send sensitive
inputs before these checks succeed. The operator must trust the installed
runtime and secure its model cache and local machine; loopback alone cannot
prove that a separately managed service does not forward data.

Run each question in a supervised worker with a hard wall-clock deadline,
request timeouts, small fixed iteration/retry and response-size limits, no
unbounded tool calls, and an explicit context budget. Reject overflow rather
than silently dropping supporting text. Terminate only the owned worker on
deadline; never publish a late result. A separately managed model server may
continue computation after client cancellation, so do not equate cancelling
the client with stopping the server. Model-related errors are safe failures,
not abstentions. Verify the exact timeout and cancellation behavior on both
supported operating systems.

**Rationale**: The official local-model route exists, but CrewAI's native
provider accepts environment-selected remote hosts and a local Ollama API
can also serve cloud models. A direct, explicitly validated boundary is safer
than relying on provider defaults. Ollama documents `OLLAMA_NO_CLOUD=1`;
`/api/tags` includes remote-model fields. A controlled runtime and local
model are needed, not merely a loopback URL.

The Ollama model catalog lists the 7B default at approximately 4.7 GB on disk.
Allow additional disk space, system RAM or VRAM for model loading, context,
embedding and the OS; the minimum depends on hardware and context and has not
been measured here. CPU inference is possible but may be slow. No question
quality, latency, or exact RAM guarantee is implied.

**Alternatives considered**: Native `ollama/` CrewAI integration is simpler,
but its endpoint, proxy, fallback, model eligibility, and timeout behaviors
would need equivalent enforcement. An external model violates the spec.
Automatic pulls violate manual preparation. Smaller local models can be
evaluated later but are not presumed equally capable.

Sources: [CrewAI local LLM docs](https://docs.crewai.com/v1.15.45/en/concepts/llms.md),
[Ollama local and cloud behavior](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features),
[model inventory API](https://docs.ollama.com/api/tags),
[Qwen 2.5 model sizes](https://ollama.com/library/qwen2.5).

## Citation freshness and source identity

**Decision**: Add a fresh opaque document revision for every successful
replacement, including identical content, transactionally with the document
and chunks. Transactionally migrate existing documents to a revision without
changing their filename, document ID, chunks, or embeddings. A retrieval
snapshot joins revision and chunk content in one committed read; retain the
public Feature 001 `Evidence` contract while adding a private versioned
retrieval path. Record an internal content digest for each cited chunk.

At publication and every subsequent applicable interaction/rerun, compare all
cited revisions and chunk digests in one fresh committed snapshot. Remove an
entire affected claim, warn, and request resubmission; unaffected claims may
remain. A failed check is a safe error, not proof of freshness. The check is
the point-in-time consistency boundary: a later commit can race with rendering
and an idle browser can be stale until the next check. Disclose this explicitly.
Do not hold database locks throughout inference or claim real-time invalidation.

**Alternatives considered**: Filename, document ID and positional chunk ID
are reused by the existing replacement code. Content digest alone cannot
detect replacement with identical content. Holding a database transaction for
the entire model call would block writes and still cannot update idle browsers.

Sources: [SQLite isolation](https://www.sqlite.org/isolation.html),
[SQLite transactions](https://www.sqlite.org/lang_transaction.html),
[Feature 001 contract](../001-knowledge-upload-indexing/contracts/knowledge-workflow.md).

## Trace privacy and permissions

**Decision**: Extend the existing explicitly constructed, allowlisted
`WorkflowTracer` and `LangfuseTraceSink`, not the CrewAI automatic integration.
Record only entered workflow/agent/task/retrieval stages, controlled status,
duration, sanitized model and numeric usage when known. Constrain the
Langfuse exporter to app-created spans and test it against the pinned SDK;
disable automatic IO/exception capture and do not forward generic CrewAI
event objects. Keep destination authorization, local confirmation, and
revocation serialization.

Only a specific explicitly selected evaluation case may add its disclosed
question and eligible filename/chunk IDs. Compare the entire indexed ordered
chunk set and metadata against chunks freshly derived from the trusted bundled
evaluation document using the same ingestion configuration. At dispatch,
recheck revision, full-content eligibility, selection and destination
authorization inside the existing serialized database dispatch boundary;
omit any unverified/unrelated identifier and warn safely. Never export document
text, digests, raw exceptions, or ordinary questions/source identifiers.
No trace permission is implied by choosing an example.

Langfuse documents that `flush()` can log failures rather than raising.
Exception-free flush is not confirmation of delivery. Implement and test a
safe bounded failure-detection path for observable transport/export errors;
report detected failures separately, distinguish unconfirmed delivery from
confirmed receipt, and never claim delivery from flush alone. Preserve
revocation semantics even on retries, shutdown, or transport failure.

CrewAI's own telemetry and AMP execution tracing are separate from Langfuse.
Ensure the selected CrewAI version cannot transmit unapproved telemetry or
content, including saved tracing consent and implicit providers. Isolate that
control from the explicitly authorized Langfuse exporter; verify with
network-denial tests. If the required isolation cannot be established, fail
closed rather than silently exporting.

**Alternatives considered**: CrewAI/OpenInference auto-instrumentation can
capture prompts and outputs. Filename-only evaluation matching permits a
same-name private replacement to leak. Retaining queued traces past revocation
violates the existing contract.

Sources: [Langfuse instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation),
[span filtering](https://langfuse.com/docs/observability/sdk/advanced-features),
[batching and flush](https://langfuse.com/docs/observability/features/queuing-batching),
[CrewAI integration](https://langfuse.com/integrations/frameworks/crewai),
[CrewAI telemetry](https://docs.crewai.com/v1.15.45/en/telemetry.md).

## UI and evaluation

**Decision**: Use a separate Streamlit view, explicit submit, per-session
request ownership and a supervised worker whose status can be observed without
restarting it on rerun. Validate on the server and enforce a single active
request atomically, not merely by disabling a button. Revalidate displayed
citations on app interactions and reruns; handle interaction paths that do
not ordinarily trigger a Streamlit rerun rather than assuming all widgets do.
Only the script thread renders UI. Provide keyboard-accessible textual status,
errors, partial answers, and source references.

Prepare original, non-sensitive, redistributable documents and at least five
independently identified cases with expected answer points and source documents,
covering three answerable, one unanswerable and one multi-source case. Run
deterministic fakes for wiring and failure tests; use an opt-in real local-model
run with human review for semantic quality. Record actual per-case outcomes,
denominators and unavailable measurements; fakes do not measure model quality.

**Alternatives considered**: Streamlit state alone is not an atomic
concurrency guard. Automatic contentful tracing of all evaluation retrievals
would leak unrelated indexed sources. A tiny sample does not support a
generalized quality claim.

Source: [Streamlit session-state behavior](https://docs.streamlit.io/develop/concepts/architecture/session-state).
