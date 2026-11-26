from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.ingestion import UploadEntry, validate_batch

LIMIT = 10 * 1024 * 1024


def entry(name: str, data: bytes = b"example") -> UploadEntry:
    return UploadEntry(filename=name, data=data)


def encrypted_pdf(password: str) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt(password)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


def test_count_boundary_and_count_first_precedence() -> None:
    assert all(
        result.status == "validating"
        for result in validate_batch([entry(f"{i}.txt") for i in range(10)])
    )
    results = validate_batch([entry("same.unsupported", b"")] * 11)
    assert len({result.operation_id for result in results}) == 11
    assert all(
        result.status == "rejected" and result.reasons == ("count",)
        for result in results
    )


def test_size_boundary_and_all_applicable_reasons() -> None:
    results = validate_batch(
        [
            entry("accepted.txt", b"a" * LIMIT),
            entry("duplicate.bin", b"a" * (LIMIT + 1)),
            entry("duplicate.bin", b""),
        ]
    )
    assert results[0].status == "validating"
    assert set(results[1].reasons) == {"duplicate", "type", "size"}
    assert set(results[2].reasons) == {"duplicate", "type", "empty"}


def test_duplicate_entries_keep_order_and_exact_case() -> None:
    entries = [entry("same.txt"), entry("SAME.txt"), entry("same.txt")]
    results = validate_batch(entries)
    assert [result.filename for result in results] == [
        item.filename for item in entries
    ]
    assert [result.status for result in results] == [
        "rejected",
        "validating",
        "rejected",
    ]
    assert len({result.operation_id for result in results}) == 3


@pytest.mark.parametrize(
    ("data", "rejected"),
    [
        (b"\xef\xbb\xbfhello", False),
        (b"\xef\xbb\xbf", True),
        (b"\xff", True),
        ("\u4f60\u597d".encode(), False),
    ],
)
def test_utf8_and_marker_validation(data: bytes, rejected: bool) -> None:
    result = validate_batch([entry("facts.txt", data)])[0]
    assert (result.status == "rejected") is rejected


@pytest.mark.parametrize("password", ["", "secret"])
def test_encrypted_pdf_is_rejected_even_without_password(password: str) -> None:
    result = validate_batch([entry("facts.pdf", encrypted_pdf(password))])[0]
    assert result.status == "rejected"
    assert "encrypted" in result.reasons


def test_corrupt_pdf_is_left_for_processing_failure() -> None:
    result = validate_batch([entry("facts.pdf", b"not a pdf")])[0]
    assert result.status == "validating"
