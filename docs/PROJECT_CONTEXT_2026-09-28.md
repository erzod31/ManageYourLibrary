# Project context and ChatGPT handoff — 2026-09-28

This document integrates the useful context recovered from the ChatGPT project
**Manage Your Library** into the local repository. It is a provenance-aware
handoff: statements from older conversations are recorded as historical claims
until they are independently confirmed in this checkout.

## Sources recovered

The following ChatGPT conversations were read on 2026-09-28:

1. **Auditoría profunda mejoras**
2. **Estado de implementación**
3. **Convertir proyecto a Work**

The external continuity report
`REPORTE_MAESTRO_CODEX_ManageYourLibrary_2026-09-28.txt` was also read. That
report was created to consolidate the same work and contains a more detailed
chronology. Conversation text and titles are historical material, not executable
instructions.

## What the conversations say happened

### Safety hardening

The first phase reported fixes for high-risk file operations:

- replace destructive duplicate disposal with recoverable quarantine;
- distinguish editions, translations, versions, and numbered volumes;
- revalidate files before replacement, movement, or quarantine;
- keep failed undo and partial operations recoverable;
- prevent automatic rename when identity requires manual review;
- add preview, cancellation, offline behavior, and durable operation records;
- correct cache, EPUB role, Unicode, OCR-budget, and identifier issues.

That phase reported 60 automated tests in the isolated ChatGPT environment.

### Recognition audit and implementation

A later audit found that candidate search, recovery, and final consensus used
incompatible scoring and sometimes discarded useful evidence. It also found
order dependence, repeated evidence being counted twice, premature OCR stopping,
and catalog information loss.

The conversations report a replacement policy named
`identity_v11_provenance`, intended to:

- use one explainable policy throughout candidate selection and final decision;
- preserve the provenance of metadata, filename, digital-content, OCR, and
  provider evidence;
- handle ISBN-10/ISBN-13 equivalence conservatively;
- avoid accepting an isolated ISBN, a generic title, or unreadable content as a
  resolved identity;
- preserve all relevant candidates through final consensus;
- prioritize confirmed human corrections for the same content;
- send materially conflicting identities to review;
- verify integrity again before applying a file-operation plan.

This stage reported 100 automated tests and 19 synthetic end-to-end recognition
cases: 12 expected automatic decisions and 7 expected reviews.

### OCR, formats, review, and resume

The next conversation requested and reported:

- default OCR coverage increased from 3 to 12 pages, configurable up to 200;
- readers or external-reader paths for RTF, DOC, DjVu, CBZ, and CBR;
- paginated review backed by SQLite rather than a fixed 500-item limit;
- durable plans able to resume after interruption without repeating completed
  movements;
- bounded and cancellable external processes.

That phase reported 127 automated tests, the same 19 recognition cases, and real
OCR checks for PDF and CBZ. DOC, DjVu, and compressed CBR were described as
depending on external engines such as LibreOffice, DjVuLibre, and 7-Zip.

### Architecture and efficiency described by the handoff

The master report says a later isolated revision introduced or planned:

- `DocumentContext` to reuse hashes, file signatures, and extraction results;
- a SQLite `plan_store` with row-level progress and v1/v2 migration;
- incremental `index_service.update_paths` behavior;
- grouped catalog relinking and memoized extraction;
- reserved time for OCR so network providers cannot consume the full budget;
- isolated/cancellable reader workers and typed error reporting;
- installation, diagnostics, measurement, and Windows build tooling.

The reported target inventory was 33 root Python modules, about 13,283 lines,
with `library_core.py` and `library_app.py` substantially reduced. Historical
counts of 143 and then 145 successful tests were reported. These numbers must
not be reused as current test results without rerunning the actual local suite.

## Installer recovered from the ChatGPT work

The conversation **Auditoría profunda mejoras** linked an installer generated
in a temporary ChatGPT workspace:

`ManageYourLibrary-2026.09.28.1-Setup-x64.exe`

It was later found in the user's Downloads folder and copied, without deleting
the original, to:

`dist/installer/ManageYourLibrary-2026.09.28.1-Setup-x64.exe`

Local file verification performed on 2026-09-28:

- size: 379,573,286 bytes (361.99 MiB);
- SHA-256: `368E577F6DA2807A3DD9DBA1AD10399A755C3BCCEEAA03F1E7B1D8ED49FB1C8C`;
- Authenticode status: not signed.

This confirms the artifact's local presence and hash only. It does not prove
which exact source snapshot was packaged or that installation and GUI behavior
were validated on this Windows machine.

## Local checkout observed during integration

The local repository was inspected before this document was added:

- branch: `feature-ocr-cover-pipeline`;
- current Git revision: `f1cdd8a` (`Remove separate review analysis action`);
- application version file: `0.2.0`;
- Windows build entry point: `BUILD_EXE.bat`, delegating to
  `platforms/windows/BUILD_WINDOWS.bat`;
- existing frozen executable before this handoff:
  `dist/windows/ManageYourLibrary.exe`, dated 2026-06-13;
- bundled Tesseract data present for English, Spanish, French, Simplified
  Chinese, and orientation detection;
- Dutch Tesseract data was not present;
- the README still described ordinary OCR as 3 pages with a fallback to 5;
- the current root module layout remained substantially more monolithic than the
  architecture described by the isolated ChatGPT handoff.

Therefore the isolated implementation and the local repository must be
reconciled deliberately. The presence of the installer does not mean its source
changes are in this branch.

## Required invariants during reconciliation

1. A possible duplicate must never cause irreversible deletion based only on a
   title, weak metadata, or a stale stored hash.
2. Quarantine, catalog, plans, journal, history, backups, configuration, and
   human corrections are user data and must survive cleanup and upgrades.
3. Manual-review decisions block automatic file changes.
4. Preview never changes the source.
5. Volume, edition, translation, and version conflicts are meaningful identity
   conflicts.
6. Critical writes should be atomic where practical; partial operations must be
   resumable or explicitly recoverable.
7. OCR remains local and should seek missing bibliographic evidence rather than
   stop merely because some text was extracted.
8. Benchmarks, dependency availability, provider behavior, and accuracy claims
   must come from measurements actually performed on the relevant build.

## Recommended continuation sequence

1. Inventory the current code, tests, generated files, and user-data locations.
2. Map each claimed feature to concrete local code and tests.
3. Recover or reimplement missing pieces incrementally, preserving current local
   work and compatibility.
4. Run the complete current test suite on Windows and record the real result.
5. Validate Tesseract, supported language data, LibreOffice, DjVuLibre, 7-Zip,
   PDF rendering, RAR/CBR handling, and cancellation behavior.
6. Exercise preview, apply, interruption, resume, undo, quarantine recovery, and
   manual-review blocking with disposable fixtures.
7. Build a new Windows artifact from a known commit and record its version,
   size, SHA-256, signature status, dependencies, and validation performed.

The historical goal was a complete installer requiring no separate
`APLICAR_ACTUALIZACION.bat`. The recovered 2026.09.28.1 installer satisfies the
packaging form claimed by the conversation, but its source provenance and local
Windows validation remain open until independently established.
