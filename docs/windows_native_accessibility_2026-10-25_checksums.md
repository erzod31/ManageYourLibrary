# Windows development validation — 2026-10-25

Development evidence only, not a new public release or a redistribution approval.
Published 0.5.3 packages were not replaced. Source revision and tested artifacts
below are specific snapshots, not a claim that arbitrary later builds are tested.

## Exact tested Windows snapshot

- Revision: `bdb476afb8049ad3a99bb7da78c69d7d668f5076` on
  `codex/audit-optimizations`, with a clean worktree at build time.
- Build-relevant source fingerprint: 268 files,
  `1A821BE04CFB8E52DAEA62F6314FE699310E1A61AF41B1E7EB3034F042D0264C`.
- Development launcher: `ManageYourLibrary.exe`, 5,147,442 bytes.
- Launcher SHA-256:
  `5984879DB4BE63547EEC312C8ED2F2FC9508957151201031E417D4E569801254`.
- Host: Windows 11, build 26300, x64. Python 3.12.10 in an isolated build venv.
- Versions installed from the Windows lock: PyInstaller 6.21.0, pypdf 6.21.2,
  pypdfium2 5.14.0, Pillow 13.0.0, ftfy 6.3.1. Full dependency hashes remain in
  `requirements.lock`; the artifact has its own build manifest.
- GUI: Tcl/Tk 9.1.0 plus CPython's 3.12 bridge, built from SHA-256-pinned sources
  listed in `tools/tk_sources.json`. No global Python/Tk replacement.
- Entry point: existing `platforms/windows/BUILD_WINDOWS.bat`, selected with
  `MANAGE_YOUR_LIBRARY_PYTHON` and a fresh development output destination.

## Results

- 494 unit/regression tests: correct, 2 skipped on Windows (symlink availability).
- Source/frozen smoke tests: correct.
- Catalog performance gate at 1,000, 10,000 and 50,000 synthetic records: correct.
  This is not a remeasurement of all UI frame-time benchmarks from October 24.
- Frozen runtime: 5/5 correct — Tk initialization, five required bundled OCR
  languages, image OCR, PDFium/PDF OCR and isolated reader/descendant OCR.
- Frozen first use: 5/5 correct — empty defaults/workspace, no background work,
  no automatic networking, fresh disposable state.
- Separate source native-API probe: 19/19 correct on Windows. Registered actions,
  disabled-action protection, selection/path values and metadata-field labels
  were tested. This is **not** external screen-reader/speech certification.
- Tcl/Tk, libtommath, zlib, utf8proc and SheenBidi legal notices are present in
  the tested GUI runtime payload. Partial matched-package OCR notices are present.

The failed first Tk 9.1 frozen attempt is not treated as passed: it exposed
missing GUI DLL collection. The corrected final build above passed both frozen
diagnostics. Earlier artifacts are retained separately and are not relabeled as
this revision. This final build did not create or validate a new installer,
upgrade or uninstall, and did not modify the usual installed application.

## macOS/Linux and limits

The earlier native test run
[40138402715](https://github.com/erzod31/ManageYourLibrary/actions/runs/40138402715)
passed Linux x64, macOS ARM64 and macOS Intel on revision `0e900c5`. The final
repeat for `bdb476a` is
[40139143087](https://github.com/erzod31/ManageYourLibrary/actions/runs/40139143087).
All three native jobs completed successfully; the publishing job was skipped.
Linux job: `121006949657`; macOS Intel: `121006949985`; macOS ARM64:
`121006950005`. The Actions artifacts retain the source native-API report,
GUI source pins, native dependency manifests, wheel locks and package checksums.
These are test artifacts, not a new published release or license clearance.
Source checks for `bdb476a` passed in
[40139143092](https://github.com/erzod31/ManageYourLibrary/actions/runs/40139143092).

Windows desktop interaction was paused when the machine locked. The Computer Use
skill requires a stop in that state. External accessible-tree labels/actions,
NVDA, VoiceOver, Orca and actual OS DPI matrices remain unvalidated. No security
or privacy settings were changed to make a test pass.

All diagnostics used synthetic disposable profiles. No books were moved/deleted
by these validation runs. Windows signing and macOS Developer ID/notarization
were not performed. The [per-DLL OCR review](LICENCIAS_OCR_2026-10-25.md) leaves
redistribution and native security review open; the project's MIT license is
not substituted for third-party licensing obligations.
