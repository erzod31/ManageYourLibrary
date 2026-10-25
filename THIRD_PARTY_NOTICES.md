# Third-Party Notices

Manage Your Library uses and/or bundles third-party components for local ebook analysis and packaging.

The project's own source is MIT licensed; see `LICENSE`. This does not relicense
the components below. An isolated Qt/PySide6 experiment was evaluated during the
technology audit; its [historical measurements](docs/validation_data_2026-10-24/qt-prototype.json)
are preserved. The experiment is not part of the maintained application or its
dependencies. A future Qt distribution would require a separate license review.

## Tesseract OCR

- Project: Tesseract OCR
- Homepage: https://github.com/tesseract-ocr/tesseract
- License: Apache License 2.0
- Purpose: Local OCR engine used for scanned PDFs and image files.

## Tesseract Language Data

- Project: tessdata / tessdata_fast
- Homepage: https://github.com/tesseract-ocr/tessdata_fast
- License: Apache License 2.0
- Included or expected models: `eng`, `spa`, `fra`, `nld`, `chi_sim`, and `osd`.

## Python Dependencies

- pypdf: PDF metadata and text extraction.
- pypdfium2 / PDFium: PDF page rendering for local OCR.
- Pillow: image preparation for OCR.
- Python standard-library `SequenceMatcher`: deterministic title and author comparison; RapidFuzz is not bundled.
- ftfy: Unicode/mojibake repair.
- pefile (Windows diagnostics): MIT; its installed metadata/license accompanies the frozen app.
- PyInstaller and its Windows helper packages: application packaging.

## Packaging tools

- PyInstaller: GPL-2.0-or-later with the PyInstaller bootloader exception.
- Inno Setup: installer generation; it is a build-time dependency and is not bundled as a runtime component.

OCR runs locally. The app does not send documents to external OCR services.

## Required image-library acknowledgements

This software is based in part on the work of the Independent JPEG Group.
This software is based in part on the work of the FreeType Team.
FreeType components are distributed under the FreeType License (FTL) option,
not its alternative GPL option. The complete applicable upstream texts remain
in the Pillow/PDFium license directories.

## Supplemental runtime evidence (development)

New builds carry the complete pinned CPython history/license document and
supplemental dependency notices under `licenses/python-runtime`, rather than
assuming the short Windows `LICENSE.txt` contains every source-level notice.
Windows collection verifies the installed Python native family against the
official hash-pinned CPython 3.12.10 AMD64 embed archive. The unmodified
`_tkinter` sources are recompiled against the isolated Tcl/Tk 9.1 runtime;
the project-specific Tk Windows repair has separate notices and source receipt.

`licenses/wheels` retains exact supplemental AVIF notices, including the AOM
license and patent text, the applicable dav1d copyright, and preserved
third-party terms. A license present in a general wheel notice/SBOM is not
by itself proof that an optional library was linked. Hash-bound Windows
wheel observations distinguish compiled features from optional components.

Windows development builds target Windows 10 or later, with the OS-provided
Universal CRT/API sets. They do not redistribute arbitrary copies from an
ambient application PATH. Selected Python, wheel, isolated GUI and controlled
OCR native inputs have a portable per-file origin/hash receipt; this is not a
legal approval, a vulnerability audit, or a waiver of Microsoft runtime terms.
The two application-local Visual C++ runtime DLLs are selected only from the
installed compiler's Microsoft desktop x64 REDIST directory, with valid
Microsoft Authenticode signatures and file versions at least as new as the
selected toolset. They replace an older Python-supplied runtime when required
by the newly compiled GUI; the receipt distinguishes these Microsoft files
from the original Python archive. Build success does not determine the owner's
Microsoft license eligibility or approve the full application release.

## Optional Windows app voice (development)

The opt-in app voice calls the installed Windows SAPI API through Python ctypes.
No speech engine, NVDA copy, or external reader is bundled or redistributed by
this feature. It starts off each session and does not change OS startup settings.

## Development-package audit, 2026-10-24

Frozen builds retain the installed wheel metadata and license files for Pillow,
pypdf, pypdfium2/PDFium, ftfy, wcwidth and the PyInstaller bootloader. The Windows
build also carries the Python distribution's `LICENSE.txt` under `licenses/python`.
Pillow's wheel includes its binary dependency notices and SBOM. These documents
are third-party attribution, not personal project-owner data.

The checked-in Windows OCR runtime identifies itself as Tesseract
`5.5.0.20241111`, with Leptonica 1.85.0 and additional DLLs. The preserved Apache
license texts cover the engine/model projects, **not every DLL in that legacy
bundle**. Exact native dependency provenance, redistribution notices/source
obligations and security review remain release blockers. A passing OCR test or
Python vulnerability scan does not clear those blockers. Development artifacts
are for local validation; they are not approved for a new public release.

Upstream sources: [engine license](https://github.com/tesseract-ocr/tesseract/blob/5.5.0/LICENSE),
[model license](https://github.com/tesseract-ocr/tessdata_fast/blob/4.1.0/LICENSE),
[Windows distributor](https://github.com/UB-Mannheim/tesseract/wiki).

## Per-DLL OCR review, 2026-10-25

The [individual review](docs/LICENCIAS_OCR_2026-10-25.md) covers 56 DLLs and
`tesseract.exe` in 44 source families. All 57 binary hashes match the original
upstream Windows installer. A further 21 binaries exactly match historical
MSYS2 packages; versions proposed by recipes for the other 36 are not presented
as confirmed build receipts. Six trained-data models match official sources.

Verbatim notices recovered from matching packages are included under
`tesseract/licenses/reviewed-package-notices`. This recovery is **partial**;
corresponding-source, complete notice and combined-work requirements remain
open. In particular, the TIFF dependency imports GPL-licensed JBIG-KIT.
Several libraries have LGPL or alternative copyleft conditions. GCC runtime
libraries carry the GCC Runtime Library Exception, not an MIT license.
The project source remains MIT; that does not clear the OCR dependency set.

That review records the **legacy** binaries; its blocked findings are preserved
as historical evidence, not silently changed into approvals.

## Replacement OCR source profile, 2026-10-25

New builds no longer distribute the legacy 57-binary Windows runtime. The old
executables/DLLs and four unused Java debugging JARs were removed from the current
source tree. No published history or older release asset was rewritten/deleted.

`tools/ocr_source_lock.json` pins source archives, SHA-256 hashes, build switches,
licenses/notices and six official model hashes. The existing platform builders
use `tools/build_permissive_ocr.py` (native staging: `bundle_native_ocr.py`).
The OCR CLI statically links only these OCR libraries:

- Tesseract 5.5.3: Apache-2.0, including preserved file-level notices.
- Leptonica 1.87.0: BSD-2-Clause, including preserved file-level notices.
- libpng 1.6.59: PNG Reference Library License v2 (`libpng-2.0`); historical text retained.
- zlib 1.3.2: Zlib license.

TIFF/JBIG, curl/archive, Pango/GLib, gettext/iconv and the other legacy OCR
dependencies are not linked or copied. This is a **replacement**, not a claim
that omitting license texts would remove obligations from existing binaries.
The app still accepts its existing image formats: Pillow normalizes them to PNG;
PDFium renders scanned PDFs before OCR. The standalone CLI is deliberately not
a general-purpose TIFF/JBIG converter, training suite, or remote URL downloader.

Each OCR payload includes full unmodified source archives, the exact recipe,
normalized build caches/commands, verbatim license/AUTHORS files and collected
source-level notices. Source archives also contain separately licensed **unbuilt**
examples/contrib programs; their GPL or other notices remain intact and do not
describe code linked into the OCR executable. The models remain Apache-2.0.

The Windows build uses Microsoft's static C/C++ runtime (`/MT`); it does not
relicense Microsoft runtime code as MIT/Apache. See the
[Microsoft redistribution terms](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)
and [Build Tools license](https://visualstudio.microsoft.com/license-terms/vs2022-ga-diagnosticbuildtools/).
Linux uses the target OS's glibc/libstdc++/libgcc baseline without copying those
libraries into this OCR payload. macOS uses its OS libraries. This OCR-specific
review is not a license clearance of all GUI/Python/PDFium package components.

`verify_ocr_payload.py` rejects modified sources/notices/models, unexpected
files and legacy DLL/JAR additions; Windows PE imports are rechecked. A verified
`ocr_libraries_profile` is separate from the overall `redistribution_review` gate,
which remains `not_complete` until the entire application release is reviewed.
The native publication job also refuses a public release until all three native
manifests record the complete redistribution review as passed. Internal tests
and an OCR-only review cannot approve a public native release.
**Older releases and historical Git objects are not retroactively cleared.**
See [resolution and validation scope](docs/RESOLUCION_GPL_LGPL_OCR_2026-10-25.md).
