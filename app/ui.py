"""Loopback-only Streamlit interface for local knowledge indexing."""

import atexit
import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

import streamlit as st
from streamlit import config as streamlit_config

from app.config import AppConfig, is_loopback_bind, load_config
from app.embeddings import LocalEmbeddings
from app.ingestion import (
    UploadEntry,
    UploadResult,
    new_upload_batch,
    process_batch,
)
from app.observability import (
    LangfuseTraceSink,
    TraceDiagnosticChannel,
    TracePermissionManager,
    WorkflowTracer,
)
from app.question_errors import user_guidance
from app.storage import SQLiteKnowledgeStore

_question_jobs = None
_owned_ollama_runtime = None
_owned_ollama_runtime_key: tuple[str, str] | None = None
_EVALUATION_DATASET = (
    Path(__file__).parents[1] / "evaluation" / "feature_002" / "cases.jsonl"
)


def _job_registry():
    global _question_jobs
    if _question_jobs is None:
        from app.question_jobs import QuestionJobRegistry

        _question_jobs = QuestionJobRegistry()
    return _question_jobs


def _ensure_ollama_runtime(config: AppConfig) -> str | None:
    global _owned_ollama_runtime, _owned_ollama_runtime_key
    from app.local_model import LocalModelError, OllamaRuntime

    key = (config.ollama_executable, config.ollama_host)
    if (
        _owned_ollama_runtime is not None
        and _owned_ollama_runtime_key == key
        and _owned_ollama_runtime.is_running
    ):
        return None
    if _owned_ollama_runtime is not None:
        _owned_ollama_runtime.__exit__(None, None, None)
        _owned_ollama_runtime = None
        _owned_ollama_runtime_key = None
    runtime = OllamaRuntime(config.ollama_executable, config.ollama_host)
    try:
        runtime.__enter__()
    except LocalModelError as exc:
        return exc.code
    _owned_ollama_runtime = runtime
    _owned_ollama_runtime_key = key
    atexit.register(runtime.__exit__, None, None, None)
    return None


def _load_ui_cases() -> list[dict[str, object]]:
    try:
        cases = [
            json.loads(line)
            for line in _EVALUATION_DATASET.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError):
        return []
    return [case for case in cases if isinstance(case, dict)]


@st.cache_resource
def _load_embeddings(model_name: str, cache_dir: str) -> LocalEmbeddings:
    return LocalEmbeddings(model_name, Path(cache_dir))


@st.cache_resource
def _trace_permissions(database: str, destination: str) -> TracePermissionManager:
    return TracePermissionManager(Path(database), destination)


def _create_tracer(
    config: AppConfig, database: Path
) -> tuple[WorkflowTracer, TraceDiagnosticChannel]:
    diagnostics = TraceDiagnosticChannel()
    if config.trace_host is None:
        return WorkflowTracer(None, diagnostics), diagnostics
    permissions = _trace_permissions(str(database), config.trace_host)
    sink = LangfuseTraceSink(
        permissions,
        diagnostics,
        public_key=config.trace_public_key,
        secret_key=config.trace_secret_key,
    )
    return WorkflowTracer(sink, diagnostics), diagnostics


def _safe_filename(filename: str) -> str:
    return "".join(
        character if character.isprintable() else "?" for character in filename
    )


def _render_trace_controls(
    config: AppConfig, permissions: TracePermissionManager | None
) -> None:
    st.subheader("Workflow trace export")
    if config.trace_host is None or permissions is None:
        st.info("Tracing is not configured. Indexing and retrieval remain available.")
        return

    st.text(f"Destination: {config.trace_host}")
    st.text(
        "Exported data: opaque operation IDs, controlled step names, status, "
        "duration, sanitized model IDs, and available numeric usage."
    )
    st.text(
        "Ordinary traces exclude questions, filenames, paths, vectors, credentials, "
        "document text, and raw exceptions. A separately confirmed evaluation "
        "trace may include its disclosed question and verified sample source IDs."
    )
    has_credentials = bool(config.trace_public_key and config.trace_secret_key)
    if not has_credentials:
        st.warning(
            "Trace export is unavailable until both Langfuse credentials are configured."
        )

    state = permissions.state
    if state.startswith("local_"):
        st.text(
            "Local confirmation applies only to this application process. Confirm "
            "that the service and its full delivery path stay on this computer, "
            "without forwarding, proxies, or tunnels. You are responsible for "
            "the receiving service's forwarding configuration."
        )
        attested = st.checkbox(
            "I confirm the local service and its full delivery path stay on this computer.",
            key="local_trace_attestation",
            disabled=not has_credentials,
        )
        if st.button(
            "Confirm local trace destination",
            key="confirm_local_trace",
            disabled=not attested or not has_credentials,
        ):
            if permissions.confirm_local(attested=True):
                st.success("Local trace destination confirmed for this process.")
            else:
                st.warning(
                    "The local destination could not be verified; trace export remains disabled."
                )
        if state == "local_confirmed":
            st.success("Local trace export is confirmed for this process.")
        if st.button(
            "Report a routing change and revoke local confirmation",
            key="revoke_local_trace",
        ):
            permissions.invalidate_route()
            st.success("Local trace confirmation revoked.")
        return

    if state == "external_disabled":
        st.info("External trace export is disabled.")
        authorized = st.checkbox(
            "I authorize sending the disclosed trace fields to this external destination.",
            key="external_trace_consent",
            disabled=not has_credentials,
        )
        if st.button(
            "Enable external trace export",
            key="enable_external_trace_export",
            disabled=not authorized or not has_credentials,
        ):
            permissions.grant_external()
            st.success("External trace export enabled for this destination.")
    else:
        st.success("External trace export is enabled for this destination.")
        if st.button(
            "Revoke external trace export",
            key="revoke_external_trace",
        ):
            permissions.revoke()
            st.success("External trace export revoked.")


def _render_results(results: list[UploadResult]) -> None:
    for result in results:
        st.text(
            f"{_safe_filename(result.filename)}: {result.status} - {result.message}"
        )


def _render_question_outcome(outcome, request_id: str) -> None:
    if outcome.status in {"complete", "partial"}:
        st.success(
            "Answer verified against the current indexed sources."
            if outcome.status == "complete"
            else "Partial answer: some information could not be verified."
        )
        for claim in outcome.supported_claims:
            st.text(claim.text)
            st.text(
                "Sources: "
                + "; ".join(
                    f"{_safe_filename(citation.filename)} (chunk {citation.chunk_id})"
                    for citation in claim.citations
                )
            )
        if outcome.missing_explanation:
            st.info(outcome.missing_explanation)
    elif outcome.status == "no_knowledge":
        st.info("No indexed knowledge is available. Index documents before asking.")
    elif outcome.status == "abstained":
        st.info(
            outcome.missing_explanation
            or "The available sources do not support a reliable answer."
        )
    else:
        st.error(user_guidance(outcome.error_code))
        st.caption(f"Operation ID: {request_id}")
    for warning in outcome.trace_warnings:
        st.warning(warning)


def _refresh_displayed_answer(store: SQLiteKnowledgeStore) -> None:
    outcome = st.session_state.get("question_outcome")
    if outcome is None:
        return
    from app.question_jobs import _freshen_outcome
    from app.question_workflow import AnswerOutcome

    try:
        refreshed = _freshen_outcome(store, outcome)
    except (OSError, sqlite3.Error):
        refreshed = AnswerOutcome(
            status="failed",
            error_code="storage_unavailable",
            trace_record=outcome.trace_record,
            trace_warnings=outcome.trace_warnings,
        )
    st.session_state["question_outcome"] = refreshed


def _render_question_view(config: AppConfig, store: SQLiteKnowledgeStore) -> None:
    st.title("Ask questions")
    st.caption(
        "Displayed answers are checked on each app rerun. An idle view can become "
        "stale until the next interaction or rerun."
    )
    question = st.text_area(
        "Question",
        key="question_input",
        max_chars=8000,
        help="Ask about information in the indexed documents.",
    )
    cases = _load_ui_cases()
    if not cases:
        st.warning("The optional evaluation cases are unavailable.")
    case_options = ["None", *(str(case["id"]) for case in cases)]
    selected_case_id = st.selectbox(
        "Optional evaluation case",
        case_options,
        key="evaluation_case",
        help="Selecting a case does not authorize trace export.",
    )
    selected_case = next(
        (case for case in cases if case.get("id") == selected_case_id), None
    )
    fields_confirmed = False
    if selected_case is not None:
        destination = config.trace_host or "No trace destination configured"
        st.info(
            "Evaluation trace disclosure: the selected question and verified "
            f"sample source filenames/chunk IDs may be sent to {destination}. "
            "No document text or content hashes are included."
        )
        st.text(f"Selected question: {selected_case.get('question', '')}")
        fields_confirmed = st.checkbox(
            "For this request, I confirm export of the disclosed question and "
            "verified sample source identifiers if the destination is authorized.",
            key="evaluation_fields_confirmed",
        )

    submitted = st.button("Submit question", key="submit_question")
    session_id = st.session_state.setdefault("question_session_id", uuid4().hex)
    if submitted:
        if not question.strip():
            st.info("Enter a question before submitting.")
        else:
            from app.question_jobs import QuestionRequest, run_question_request

            request_id = uuid4().hex
            use_case_id = (
                str(selected_case["id"])
                if selected_case is not None
                and question.strip() == selected_case.get("question")
                else None
            )
            try:
                has_documents = store.has_documents()
            except (OSError, sqlite3.Error):
                has_documents = False
            runtime_error_code = (
                _ensure_ollama_runtime(config) if has_documents else None
            )
            request = QuestionRequest(
                request_id=request_id,
                question=question.strip(),
                config=config,
                evaluation_case_id=use_case_id,
                evaluation_fields_confirmed=fields_confirmed
                and use_case_id is not None,
                runtime_error_code=runtime_error_code,
            )
            if _job_registry().submit(
                session_id, request_id, run_question_request, request
            ):
                st.session_state["question_request_id"] = request_id
                st.session_state["question_submitted_text"] = question.strip()
                st.session_state["question_outcome"] = None
            else:
                st.info("A question is already processing. Wait for it to finish.")

    request_id = st.session_state.get("question_request_id")
    outcome = st.session_state.get("question_outcome")
    if request_id and outcome is None:
        from app.question_workflow import AnswerOutcome

        progress = st.status("Processing your question...", state="running")
        while True:
            snapshot = _job_registry().poll(session_id, request_id)
            if snapshot is None:
                outcome = AnswerOutcome(status="failed", error_code="workflow_failed")
                break
            if snapshot.state != "running":
                outcome = snapshot.outcome or AnswerOutcome(
                    status="failed", error_code="workflow_failed"
                )
                break
            time.sleep(0.2)
        progress.update(
            label=(
                "Question processing finished."
                if outcome.status != "failed"
                else "Question processing failed."
            ),
            state="complete" if outcome.status != "failed" else "error",
            expanded=False,
        )
        st.session_state["question_outcome"] = outcome
    else:
        outcome = st.session_state.get("question_outcome")

    if outcome is not None:
        from app.question_jobs import _freshen_outcome

        try:
            outcome = _freshen_outcome(store, outcome)
        except (OSError, sqlite3.Error):
            _refresh_displayed_answer(store)
            outcome = st.session_state.get("question_outcome")
        st.session_state["question_outcome"] = outcome
        _render_question_outcome(outcome, request_id or "")


def main() -> None:
    st.set_page_config(
        page_title="Knowledge assistant", page_icon=":material/library_books:"
    )
    address = streamlit_config.get_option("server.address")
    if not is_loopback_bind(address):
        st.error(
            "Unsafe or unset server binding. Start the app with run.ps1, which "
            "binds explicitly to 127.0.0.1."
        )
        st.stop()

    try:
        config = load_config()
    except ValueError:
        st.error(
            "Application configuration is invalid; check the environment settings."
        )
        st.stop()

    st.session_state.setdefault("upload_epoch", 0)
    st.session_state.setdefault("upload_results", [])
    database = config.knowledge_dir / "knowledge.sqlite3"
    store = SQLiteKnowledgeStore(database)
    tracer, diagnostics = _create_tracer(config, database)

    st.title("Knowledge upload and indexing")
    st.caption(
        "Documents and embeddings stay in the configured local knowledge base. "
        "The local embedding model may need to download once before offline use."
    )
    st.subheader("Indexing privacy")
    st.info(
        "The configured FastEmbed model processes document text locally. "
        "No external indexing provider is configured; indexing authorization "
        "is separate from workflow trace export."
    )
    permissions = (
        _trace_permissions(str(database), config.trace_host)
        if config.trace_host is not None
        else None
    )
    view = st.segmented_control(
        "Application view",
        ["Upload", "Ask questions"],
        default="Upload",
        key="app_view",
    )
    _refresh_displayed_answer(store)
    _render_trace_controls(config, permissions)
    if view == "Ask questions":
        _render_question_view(config, store)
        return

    st.title("Knowledge upload and indexing")
    st.subheader("Upload files")
    st.caption(
        "Submit up to 10 UTF-8 text or unencrypted text PDF files. "
        "The application limit is 10 MiB per file."
    )
    with st.form("knowledge_upload_form"):
        files = st.file_uploader(
            "Select knowledge files",
            accept_multiple_files=True,
            key=f"knowledge_files_{st.session_state['upload_epoch']}",
            max_upload_size=11,
        )
        submitted = st.form_submit_button("Index selected files", key="submit_uploads")

    if submitted:
        entries = [
            UploadEntry(upload.name, upload.getvalue()) for upload in (files or [])
        ]
        if not entries:
            st.info("Select at least one file before submitting.")
            st.session_state["upload_results"] = []
        else:
            batch = new_upload_batch(entries)
            status_slots = {
                operation_id: st.empty() for operation_id in batch.operation_ids
            }

            def show_status(result: UploadResult) -> None:
                status_slots[result.operation_id].text(
                    f"{_safe_filename(result.filename)}: "
                    f"{result.status} - {result.message}"
                )

            results = process_batch(
                batch,
                store,
                None,
                on_status=show_status,
                tracer=tracer,
                provider_factory=lambda: _load_embeddings(
                    config.embedding_model, str(config.model_cache_dir)
                ),
            )
            st.session_state["upload_results"] = results
            st.session_state["upload_epoch"] += 1
            for slot in status_slots.values():
                slot.empty()
            _render_results(results)
            for result in results:
                for diagnostic in diagnostics.get(result.operation_id):
                    st.warning(diagnostic.message)
    elif st.session_state["upload_results"]:
        _render_results(st.session_state["upload_results"])


if __name__ == "__main__":
    main()
