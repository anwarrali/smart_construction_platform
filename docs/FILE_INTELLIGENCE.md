# File intelligence — one answer to "what is this file?"

The platform ingests IFC models, PDFs, drawings, spreadsheets, photos and
audio. Each path grew its own handling, and two gaps followed.

**Identity.** Every uploader checked that a file's bytes matched the extension
it claimed. That is a security gate: it answers yes or no, and never records
what the file actually *is*. Nothing downstream could act on the format without
re-deriving it from the filename.

**Kind.** `documents.document_type` was whatever the uploader picked from a
dropdown, defaulting to `other`. Nothing had ever looked inside a file to agree
or disagree — and there was no "bill of quantities" in the list to pick. A BOQ
filed as "other" was invisible to anything reasoning about document types.

`app/services/file_intelligence.py` supplies both, plus a registry that states
what can be extracted from each format and where the result goes.

## The stages

```
UPLOAD      save_upload / save_private_upload      (unchanged)
IDENTIFY    identify_format(bytes)                 → PDF | IFC | DWG | XLSX | …
CLASSIFY    classify_document(...)                 → BOQ | DRAWING | … + evidence
VALIDATE    _matches_signature + per-type limits   (unchanged)
EXTRACT     per-format handler named in REGISTRY
NORMALIZE   into that format's own destination
INDEX       RAG, for formats declared indexable
STORE       UPLOAD_DIR or private storage          (unchanged)
AVAILABLE   documents / IFC / RAG APIs
```

Only IDENTIFY and CLASSIFY are new. The others already existed; the registry
writes down which of them apply to which format, so "we accept this file and
extract nothing from it" is a visible, testable statement rather than something
a reader has to infer from missing code.

## Identification

`identify_format(content, extension=None)` reports what the bytes are,
independent of what they were called. A PDF renamed `.xlsx` is reported as a
PDF.

The magic-byte table (`FORMAT_SIGNATURES`) is the **single source of truth**:
`file_storage._matches_signature` now consults it instead of carrying its own
copy. Two copies of that knowledge is how an upload gate and a classifier end
up disagreeing about the same bytes. The gate's behaviour is unchanged, and
`tests/test_file_intelligence.py` proves it by running the old implementation
and the new one against every extension × payload combination.

Some formats share a container magic and genuinely cannot be told apart from
bytes alone — `.docx` and `.xlsx` are both ZIP archives, `.doc` and `.xls` are
both OLE2. There the extension is accepted as the discriminator, exactly as
before, and it is never allowed to override a signature that already matched
something else.

## The registry

`REGISTRY` declares, per format: whether text can be extracted, whether it is
indexable, where extracted information lands, and what handles it. A format
with no destination must carry a `limitation` saying why — enforced by test.

| Format | Extracted | Destination | Notes |
| --- | --- | --- | --- |
| IFC | full deterministic parse | `ifc_elements`, `ifc_spatial_nodes`, `ifc_coordination_findings` | Not a "document"; never RAG-indexed |
| PDF | text per page | `document_chunks` | Indexable. A scan with no text layer cannot be indexed; OCR is not supported |
| DWG | nothing | — | Stored and downloadable only. See below |
| DOCX / XLSX | nothing | — | No Word or spreadsheet reader is installed |
| TEXT | readable | — | Plain-text indexing is not wired into RAG |
| JPEG / PNG / WEBP | nothing | `media_assets` | Images are evidence, not text |

Audio and legacy Office containers are deliberately outside the registry: they
carry no project document content, and listing them would imply an extraction
path that does not exist.

### Why DWG is not parsed

Phase 3 asked not to build DWG support unless the architecture was ready *and*
the evidence showed it was useful. `.dwg` uploads are accepted today and
nothing has ever extracted from them, so nothing regresses by leaving that
alone. DWG is a closed binary format: reading it needs a licensed SDK or an
external converter, which is a deployment dependency rather than a library
choice. DXF would be the cheaper first step if the project turns out to need
it. The registry records that decision where a reader will find it.

## Classification

`classify_document(...)` returns a kind with the evidence that produced it.
Evidence is weighed by how much it proves:

1. **Content** (0.9) — wording inside the document. Strongest, and the reason
   PDFs get their first two pages sampled.
2. **Format** (0.8) — a DWG is a drawing whatever it is named.
3. **Filename** (0.7) — weaker, but usually deliberate.

Terms are matched as whole phrases on normalised text, in English and Arabic,
so "the works were invoiced separately" is not an invoice. Within a kind the
longest matching phrase wins, so a document that says "drawing register" is
recorded as having said that rather than merely "drawing".

**Nothing is guessed.** A document with no recognisable evidence comes back as
`OTHER` at confidence 0.2 with `evidence: null` — a truthful "I don't know"
rather than a plausible-looking label.

**Classification is advisory.** The uploader's `document_type` remains the
stored, authoritative value. The classifier's opinion is kept beside it in
`suggested_document_type` and `classification_json`, and
`disagreesWithDeclared` flags the cases where the two differ — except when the
declared type is `OTHER`, which is the form's default rather than a decision,
and flagging it would make the flag meaningless.

Classification can never fail an upload. The file is already stored and the row
is about to be written; a classifier that could not read a PDF is a missing
second opinion, not a reason to reject work someone successfully submitted.

## Document kinds

`DocumentType` gained `BOQ`, `SCHEDULE` and `TECHNICAL`. A bill of quantities
and a construction programme are among the most consequential documents on a
project and previously had nowhere to go but "other".

Migration `a03e6f9c5b48` adds the enum values and the three columns. Existing
rows are left NULL rather than backfilled: no classification was run for them,
and inventing one would be indistinguishable from having actually looked.

## What this does not do

- No OCR. A scanned PDF has no text layer and is not classified from content —
  it falls back to filename evidence.
- No spreadsheet or Word parsing, so a BOQ delivered as `.xlsx` is classified
  from its filename and stored, not read.
- Classification samples two pages. A document that only announces itself on
  page 40 is classified from its filename instead.
- Nothing is re-classified retroactively. Only new uploads carry it.
