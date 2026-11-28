"""Safe user guidance for question workflow failures."""

_GUIDANCE = {
    "local_model_unavailable": (
        "The local answer model is unavailable. Follow the documented manual "
        "Ollama and model setup steps, then retry."
    ),
    "local_model_config_invalid": (
        "The local model configuration is invalid. Check the loopback-only "
        "Ollama settings and retry."
    ),
    "input_too_large": (
        "The question and retrieved evidence exceed the model's input limit. "
        "Try a narrower question or reduce the evidence limit."
    ),
    "index_incompatible": (
        "The knowledge index uses an incompatible embedding model. Follow the "
        "documented index recovery steps and re-index the sources."
    ),
    "storage_unavailable": (
        "The knowledge index could not be read. Check the configured knowledge "
        "directory and retry."
    ),
    "local_model_timeout": (
        "The local model timed out. Retry with less evidence or after the model "
        "service has recovered."
    ),
    "worker_timeout": (
        "The question workflow exceeded its time limit. Retry with a narrower "
        "question or after the local model has recovered."
    ),
    "invalid_citation": (
        "The generated answer could not be verified against the retrieved "
        "sources. Please retry."
    ),
    "workflow_failed": (
        "The question workflow could not verify an answer. Retry; if the issue "
        "continues, contact the maintainer with the operation ID."
    ),
    "trace_disabled": (
        "The answer is unaffected. Check the trace destination authorization "
        "settings if trace export is required."
    ),
    "trace_unavailable": (
        "The answer is unaffected. Check Langfuse configuration and service "
        "availability if trace export is required."
    ),
    "trace_export_failed": (
        "The answer is unaffected. Check trace destination configuration and "
        "authorization if export keeps failing."
    ),
    "trace_unconfirmed": (
        "The answer is unaffected. Trace delivery could not be confirmed; check "
        "the destination if confirmation is required."
    ),
}


def user_guidance(error_code: str | None) -> str:
    """Return a fixed, content-free message for a controlled error code."""
    if error_code is None:
        return ""
    return _GUIDANCE.get(
        error_code,
        "The question workflow failed. Retry; if the issue continues, contact "
        "the maintainer with the opaque operation ID.",
    )
