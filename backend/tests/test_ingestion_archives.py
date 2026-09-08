"""Archive defences. Every test here is an attack that must not work.

A design package is the most hostile input the platform accepts, and these are
the four ways in: escaping the package, exhausting memory by expansion,
exhausting it by entry count, and recursing forever. Each has its own ceiling
in `services/ingestion/archives.py` because a single combined limit is defeated
by whichever dimension it does not measure.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.core.config import settings
from app.services.ingestion import archives
from app.services.ingestion.errors import (
    ARCHIVE_CORRUPTED, ARCHIVE_EXPANSION_LIMIT, ARCHIVE_TOO_MANY_ENTRIES,
    ARCHIVE_UNSAFE_ENTRY, IngestionRejected,
)

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"


def build(entries, *, compression=zipfile.ZIP_DEFLATED) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    buffer.seek(0)
    return buffer


def build_raw(names_and_payloads) -> io.BytesIO:
    """Write entries whose names bypass ZipFile's own normalisation.

    `writestr` sanitises some names, which would make a traversal test pass for
    the wrong reason. Setting `ZipInfo.filename` directly writes the hostile
    name into the central directory exactly as an attacker's tool would.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in names_and_payloads:
            info = zipfile.ZipInfo()
            info.filename = name
            archive.writestr(info, payload)
    buffer.seek(0)
    return buffer


def inspect(buffer):
    with zipfile.ZipFile(buffer) as archive:
        return archives.inspect(archive)


# --- Path traversal ---------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    [
        "../escape.pdf",
        "../../../../etc/passwd",
        "drawings/../../escape.pdf",
        "/absolute.pdf",
        "C:\\Windows\\System32\\evil.pdf",
        "..\\..\\escape.pdf",
    ],
)
def test_an_entry_that_points_outside_the_package_condemns_the_archive(name):
    with pytest.raises(IngestionRejected) as refusal:
        inspect(build_raw([(name, PDF)]))
    assert refusal.value.code == ARCHIVE_UNSAFE_ENTRY


def test_a_null_byte_in_an_entry_name_is_refused():
    """Checked directly, because `zipfile` truncates such a name on read.

    CPython's reader stops at the null and hands back `plan`, so this attack
    cannot be staged through `zipfile` at all. The check stays regardless — a
    defence must not depend on which reader happens to sit in front of it — and
    is exercised where it actually lives.
    """
    with pytest.raises(IngestionRejected) as refusal:
        archives.safe_entry_name("plan\x00.pdf")
    assert refusal.value.code == ARCHIVE_UNSAFE_ENTRY


def test_a_symlink_entry_is_refused():
    """A link's "content" is a path to follow — a traversal by another route."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("link.pdf")
        info.external_attr = (0o120777 << 16)
        archive.writestr(info, "/etc/passwd")
    buffer.seek(0)
    with pytest.raises(IngestionRejected) as refusal:
        inspect(buffer)
    assert refusal.value.code == ARCHIVE_UNSAFE_ENTRY


def test_a_leading_current_directory_prefix_is_trimmed_without_eating_a_dotfile():
    """`lstrip("./")` would rename `.DS_Store` to `DS_Store` and defeat the
    check that skips it. Only the `./` prefix is removed."""
    assert archives.safe_entry_name("./ARCH/plan.pdf") == "ARCH/plan.pdf"
    assert archives.safe_entry_name(".DS_Store") == ".DS_Store"


def test_a_nested_directory_name_survives_as_a_label():
    inspection = inspect(build([("ARCH/GF/plan-01.pdf", PDF)]))
    assert len(inspection.entries) == 1
    entry = inspection.entries[0]
    assert entry.filename == "plan-01.pdf"
    assert entry.directory == "ARCH/GF"


# --- Expansion --------------------------------------------------------------

def test_a_zip_bomb_is_refused_on_its_compression_ratio(monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_ZIP_MAX_RATIO", 10)
    with pytest.raises(IngestionRejected) as refusal:
        inspect(build([("bomb.txt", b"\x00" * (2 * 1024 * 1024))]))
    assert refusal.value.code == ARCHIVE_EXPANSION_LIMIT


def test_declared_total_expansion_over_the_ceiling_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_ZIP_MAX_TOTAL_MB", 1)
    monkeypatch.setattr(settings, "INGESTION_ZIP_MAX_RATIO", 100000)
    with pytest.raises(IngestionRejected) as refusal:
        inspect(build([(f"f{index}.txt", b"\x00" * (400 * 1024)) for index in range(5)]))
    assert refusal.value.code == ARCHIVE_EXPANSION_LIMIT


def test_a_single_oversized_entry_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_ZIP_MAX_ENTRY_MB", 1)
    monkeypatch.setattr(settings, "INGESTION_ZIP_MAX_RATIO", 100000)
    with pytest.raises(IngestionRejected) as refusal:
        inspect(build([("huge.txt", b"\x00" * (3 * 1024 * 1024))]))
    assert refusal.value.code == ARCHIVE_EXPANSION_LIMIT


def test_too_many_entries_is_refused_before_any_are_read(monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_ZIP_MAX_ENTRIES", 3)
    with pytest.raises(IngestionRejected) as refusal:
        inspect(build([(f"f{index}.txt", b"x") for index in range(10)]))
    assert refusal.value.code == ARCHIVE_TOO_MANY_ENTRIES


def test_reading_an_entry_is_bounded_independently_of_its_declared_size():
    """The header is attacker-controlled too, so the read has its own ceiling.

    Stored rather than deflated so the ratio guard does not refuse the archive
    first; this test is about the *read* limit, not the inspection limits.
    """
    buffer = build([("data.txt", b"y" * 4096)], compression=zipfile.ZIP_STORED)
    with zipfile.ZipFile(buffer) as archive:
        entry = archives.inspect(archive).entries[0]
        with pytest.raises(IngestionRejected) as refusal:
            archives.read_entry(archive, entry, limit=100)
    assert refusal.value.code == ARCHIVE_EXPANSION_LIMIT


# --- Ordinary packages ------------------------------------------------------

def test_a_real_package_is_read_and_its_noise_is_skipped_not_refused():
    inspection = inspect(build([
        ("ARCH/plan-01.pdf", PDF),
        ("STRUCT/", b""),
        ("__MACOSX/._plan-01.pdf", b"junk"),
        (".DS_Store", b"junk"),
        ("empty.pdf", b""),
        ("SPEC/specification.pdf", PDF),
    ]))
    assert sorted(entry.filename for entry in inspection.entries) == [
        "plan-01.pdf", "specification.pdf",
    ]
    reasons = {item["reason"] for item in inspection.skipped}
    assert reasons == {"ARCHIVE_METADATA", "EMPTY_ENTRY"}


def test_skipping_is_recorded_rather_than_silent():
    inspection = inspect(build([("plan.pdf", PDF), (".DS_Store", b"junk")]))
    assert [item["name"] for item in inspection.skipped] == [".DS_Store"]


def test_a_damaged_archive_reports_one_clear_failure():
    with pytest.raises(IngestionRejected) as refusal:
        archives.open_archive(io.BytesIO(b"PK\x03\x04 this is not really a zip"))
    assert refusal.value.code == ARCHIVE_CORRUPTED


def test_an_uncompressed_entry_is_not_treated_as_a_bomb():
    """Ratio is 1.0 for stored entries; the absolute ceilings still apply."""
    inspection = inspect(build([("plan.pdf", PDF)], compression=zipfile.ZIP_STORED))
    assert inspection.entries[0].compression_ratio == 1.0
