# Windows 0.5.3 checksums — Indra OCR

Local build and verification: 2026-10-28. No upload, release, tag or installation
was performed. This is a new local 0.5.3 build of this checkout, not a claim about
any other checkout or previously published package.

## Artifacts and provenance

Application: `dist/windows/ManageYourLibrary/ManageYourLibrary.exe`

SHA256: `1F8FE510C92D3CDC2E89F54A429E9C9E8000FA2467233B1EC16C8F992FBC9162`

| Release artifact in `dist/release/` | Bytes | SHA-256 |
| --- | ---: | --- |
| `ManageYourLibrary-0.5.3-Setup-x64.exe` | 126,031,749 | `B8AC5A381B385904F32079086288077E70EB7350AA8299DA21532AF0F85A59CF` |
| `ManageYourLibrary-0.5.3-Windows-x64-portable.zip` | 155,490,818 | `6F02A5A2DAD99415CBFEA555EB45192CF10E42D97774B016D6266EC315CE0633` |
| `build-manifest-0.5.3.json` | 2,302 | `6860EFBF5E3556C7462DCF01A3BC6C9FF0ED17915BB48D9F51FC66E091396119` |

- Windows x64; Python 3.12.10; PyInstaller 6.21.0; Inno Setup 6.7.3.
- Git base: `0480074649b2a8c638ca9175dcfea9708bed0a10` with the working-tree changes recorded
  in the artifact manifest. These changes are not committed or published.
- Source/config fingerprint: 235 files,
  `4F8E95F07C707EC42E98268FD4192D9F070F59297509B2885F9992FEF2DC5E45`.
- Indra OCR 1.1.2; ONNX Runtime 1.31.1; OpenCV headless 5.0.0.93; NumPy 2.5.4.
- 33 dependency wheels pinned in requirements.lock and checked against PyPI
  SHA-256 metadata. Model revision
  `bd02167fdf2005a19962cc15188f8496a2c87d3b`: 13 files, 76,104,348 bytes,
  including its license, checked against data/indra_ocr_models.json.
- Canonical commands: platforms/windows/BUILD_WINDOWS.bat,
  platforms/windows/BUILD_INSTALLER.bat, python tools/package_windows_release.py.
  The build used an isolated venv via MANAGE_YOUR_LIBRARY_PYTHON and disposable
  APPDATA, LOCALAPPDATA and temporary folders. No global packages were installed.

## Checks actually completed

- **404 tests passed in 18.203 seconds** in the final canonical Windows build.
  Source smoke, catalog performance gate, frozen smoke, four frozen runtime
  checks and all five frozen first-use checks passed.
- First-use testing creates the real Tk App with an empty temporary profile.
  It verifies no automatic operation/network request, no selected library, no
  catalog/history/plans, and no OCR worker or ONNX import at UI startup.
- Independent innounp 2.67.11 extraction of the final installer: all
  1,198 payload files (289,521,125 bytes) match the built app by SHA-256.
  The payload is unchanged after diagnostics.
- The extracted EXE passed smoke, runtime and first-use diagnostics with
  isolated state and a Windows-only PATH, with no Python/Node on PATH.
- The actual frozen OCR worker recognized expected titles in seven synthetic
  images: English, Spanish, French, Dutch, Chinese, dark and rotated covers.
  The short Chinese title regression reads both 三体 and 刘慈欣.
- A two-page scanned PDF with only an ISBN on page one continued to page two
  and recovered title/author evidence. The source mutation and page-limit cache
  regressions passed.
- The same frozen worker was reused between different pages. Actual cancellation
  during frozen worker startup completed in 204.78 ms; the next request
  restarted successfully. Unit tests additionally cover timeout, cancellation
  while queued, invalid protocol, bounded cache eviction and idle shutdown.
  Idle shutdown is tested with a shortened timer; production uses 60 seconds.
- Text and geometry share one page inference. Up to eight weak short lines may
  receive one recognition-only retry; no repeated detection/PSM/language loop.
  One worker uses at most four threads, capped at half the available CPU count.
  Python network access is denied inside the OCR worker; ONNX telemetry is disabled.
- No Tesseract, traineddata, JBIG-KIT or FFmpeg files are in the new payload.
  The optional OpenCV video plugin was excluded, removing 30,876,160 bytes.
- Model terms, attribution, Apache code license, ONNX notices, Python/Tcl/Tk
  notices and dependency license metadata accompany the payload. The installer
  embeds model-license acceptance and an attribution/use notice. Model weights
  are unmodified. The user explicitly chose full replacement with the model
  conditions. See [model terms](../third_party/indra/MODEL_LICENSE.txt) and
  [notice](../third_party/indra/NOTICE.txt).
- Portable ZIP CRC and existing clean-payload/source-fingerprint gates passed.
  Existing 0.5.2 installers/ZIP and useful intermediate builds were preserved.
- Ruff critical checks including unused imports passed for changed Python
  files; git diff --check passed. A repository-wide F401 check still reports
  the pre-existing unused guardar_indice import in library_app.py, which was
  outside this OCR change. Linux/macOS shell syntax and workflow YAML parse.

## Measured OCR comparison

The complete old image OCR workflow and the new frozen OCR workflow ran
sequentially on identical synthetic covers, three repetitions per case.
Indra's inference cache was cleared before every sample; its model worker
remained loaded. Medians are milliseconds.

| Fixture | Previous workflow | Frozen Indra | Ratio |
| --- | ---: | ---: | ---: |
| dark.png | 1423.60 | 69.49 | 20.5x |
| dutch.png | 1721.42 | 66.95 | 25.7x |
| english.png | 1306.13 | 66.81 | 19.5x |
| french.png | 1291.12 | 68.50 | 18.8x |
| rotated.png | 1919.00 | 89.66 | 21.4x |
| spanish.png | 1704.43 | 66.70 | 25.6x |

The first frozen model/process load took 969.24 ms in this run.
These are six synthetic cover comparisons on this machine, with the OS file
cache uncontrolled, not universal engine benchmarks or real-library accuracy
measurements. The seventh (Chinese) case is an additional correctness check.
The new payload is larger than the old 222,369,747-byte application folder:
local neural models and their runtime dependencies trade package size for
substantially lower warm OCR latency in these cases.

Detailed local evidence is retained outside Git in dist/indra-qa/: final-verification.json,
comparison-final.json, thread-benchmark.json, the final build/installer logs
and verify_release.py. Report SHA-256:

- final-verification.json: `49760BDF5CC471134BCA05066E82FB75581B6B1D59DDE07CA97B7D9B272030D7`
- comparison-final.json: `4307E41E417EFF20CAA41A0D2E14E518E0ACF75A2706C97BAF6C332D1B85654E`
- verify_release.py: `E1144F2DE2168D19661973F3B387DC1CDE58E547B24437DE9A7CB6E30C257DEA`

## Limits and remaining validation

- **installationTested=false**. This shared Windows must not run the installer,
  upgrade or uninstaller, even with an alternate destination. Only extraction,
  static setup review and isolated payload execution were performed.
- **isolatedLaunchTested=true**. Actual installed shortcuts, update/uninstall data
  preservation and a manual installed UI session are not certified by these checks.
- The installer is unsigned (Authenticode NotSigned).
- Native Linux/macOS execution/builds were not run for this change; those scripts
  and source CI were prepared but no remote CI was triggered. Validate them before
  publishing packages for those systems, including their native dependency notices.
- Component notices were packaged; this task does not replace any separate
  redistribution eligibility review for inherited components or grant universal
  commercial rights to the Indra models/output.
- No personal library, settings, catalog, quarantine, history, backups, pending
  plans or human corrections were removed. Only synthetic fixtures were used.
