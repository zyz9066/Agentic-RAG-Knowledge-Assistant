"""Loopback-only Streamlit interface for local knowledge indexing."""

from pathlib import Path

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
from app.storage import SQLiteKnowledgeStore


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
        "Document text, questions, filenames, paths, vectors, credentials, and "
        "raw exceptions are never included."
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
    _render_trace_controls(config, permissions)

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
