# Constructs report: evidence and verification summary

Report: `Constructs_Graduation_Project_Report.docx` (72 pages). This is a reviewed draft for the author's review, not an approved final version.
Generated on 24 October 2026 from branch `feat/ingestion-reliability`, **including its uncommitted working-tree changes** (221 changed or untracked paths at the time).

## Folder contents

| Path | Content |
| --- | --- |
| `Constructs_Graduation_Project_Report.docx` | Main editable report; fields updated by Microsoft Word |
| `Constructs_Graduation_Project_Report_preview.pdf` | PDF exported by Word, used for page-by-page inspection |
| `Constructs_Traceability_Matrix.xlsx` / `.csv` | 30 functional + 15 non-functional requirements → evidence, tests, status |
| `diagrams/` | 25 figures: editable sources (`src/`, 24 PlantUML + 1 Python) and rendered PNGs; `README.md` maps figure numbers to files |
| `evidence/` | Raw test logs, JUnit XML, per-area aggregation |
| `supporting/MODULE_INVENTORY_AND_FUTURE_TESTS.md` | Verified module inventory and future test scenarios |
| `build/` | Generator (`build.py`, `engine.py`, `content_*.py`), Word finalizer, PDF inspector |

## Inputs inspected

- University template (`Software Project Template.docx`): cover, six chapters, appendices A–C. All preserved; appendices D–E and sections 2.4 (research gap) and 4.4 (end-to-end scenarios) were added.
- Original proposal (`SmartConstructionPlatform_Proposal.pdf`): problem, objectives, stakeholders, 14 feature areas.
- Syntropy reference report (`Software Project Final Report .pdf`, 53 pages): used **only** for presentation conventions (Times New Roman body, institutional header, chapter-numbered captions, requirements as grouped lists). No content was reused.
- Previous Constructs report (`Graduation_Project_Final_Report.docx`): audited, not trusted. Corrections below.
- Repository: backend (`api`, `services`, `models`, `core`, `ai`), migrations, tests, frontend features, mobile features, docs, Docker files, Git history.

## Tests run and actual results (24 Oct 2026)

No source file changed between these runs and report generation (checked by file modification times).

| Suite | Result | Notes |
| --- | --- | --- |
| Backend (pytest) | 2,798 collected: 2,796 passed, 1 failed, 1 skipped | Isolated throwaway `pgvector/pgvector:pg15` container, never the dev database; no OpenAI key provided |
| Web (Vitest) | 294 / 310 passed in the full run | All 16 failures were 5-second timeouts under load; the 65 tests in the 9 affected files all passed when re-run serially |
| Mobile (flutter test) | 141 / 141 passed | |

- **Failed (environment-dependent):** `test_rag_ingested_files::test_the_background_job_indexes_and_closes_its_own_session` calls the real embedding API and needs a live key. Not re-run with a key, to avoid sending data to a paid external service. Reported as a failure, not a pass.
- **Skipped:** `test_ifc_worker_failure::test_a_real_truncated_ifc...` runs only when explicitly enabled.
- **Not executed:** manual QA plan, live AI-provider behaviour, Firebase push delivery, performance, load and security penetration tests. Code coverage was not measured.

## Verified (code read and tests passing)

Permission resolution and external-party ceilings; task lifecycle and review; CPM with FS/SS/FF/SF and lags; durable job queue; file ingestion state machine; RAG retrieval with authorised id sets and record-built citations; deterministic question routing; IFC processing transitions; GlobalId revision comparison and impact suggestions (linked items at confidence 1.0, same-discipline fallback at 0.65); interference candidates to issues; model-derived task and milestone suggestions; voice confirmation flow; audit and AI action history.

## Partial, disabled or not implemented

- **FR-08 budget:** budget fields and cost-validation review exist; expense records linked to evidence do not.
- **FR-19 3D viewer:** geometry generation works; `IFCViewer.tsx` and `three` exist in the last commit but are deleted in the working tree.
- **FR-23 event-driven agents:** implemented and tested; `AGENT_AUTO_ANALYSIS_ENABLED=false` by default.
- **Not implemented:** document-to-document contradiction detection, a Telegram channel (enumeration only), DWG parsing (out of scope by design). The `IFC_AI_MODEL` setting exists but no module uses it.

## Corrections relative to the previous report

- The five agents and the insight engine are **deterministic rule-based analyzers**, not LLM calls. Only six modules call OpenAI (four voice, two RAG).
- IFC impact suggestions are **acknowledged or dismissed**; the separate model-derived task/milestone suggestions are what create records when accepted.
- IFC revision comparison runs **synchronously in the request**, not as a background job.
- Project name changed to **Constructs**. The title was refined from "AI-Driven" to **"AI-Assisted"**, because most of the intelligence is deterministic and AI never acts without confirmation.
- Requirements were restructured into 30 grouped FRs, and NFRs are grouped by strength of evidence. Tables were reduced from 23 to 5.
- The product comparison now cites vendor help/support documentation (Procore Assist, Procore Models, Autodesk Model Coordination) where available, and states that "Not found" is not evidence of absence.

## References

All 47 references are cited and were verified: DOIs via the Crossref API (abstracts were checked where available, e.g. Oraee 2019, Saka 2024, Awe 2025, and Shen 2010 from the NRC open-access copy), arXiv IDs via the arXiv API, RFCs via rfc-editor.org, and ISBNs via Open Library (PMBOK via a catalogue search). Four papers had no retrievable abstract (Erfani 2026, Zheng & Fischer 2023, Wefki 2024; Shen 2010 was read from the PDF). For the first three, the claims made are limited to what their titles establish.

## Decisions to review

1. **Supervisor name:** the proposal writes "Prof. Salah Aldeen Odeh"; the Syntropy report (same department) writes "Prof. Dr. Eng. Salaheddin Odeh". The cover uses the latter. Please confirm the official form.
2. **Title:** "Constructs: An AI-Assisted Construction Intelligence and Collaboration Platform for Design-to-Execution Integration" (refined from "AI-Driven"; see above).
3. **Dedication and acknowledgement:** highlighted placeholders; only the author can write them.
4. **Cover logo:** the Syntropy report has the university logo, but the template does not. It was not added; insert the official logo if the department requires it.
5. **3D viewer:** update FR-19 once the working-tree deletion is committed or reverted.
6. **Regeneration:** rerunning `build/build.py` overwrites manual edits in the .docx; edit the `content_*.py` files instead, or edit only the final .docx.
