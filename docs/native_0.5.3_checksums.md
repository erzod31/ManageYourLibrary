# Native 0.5.3 supplement 2: build evidence

Published release: [v0.5.3-native.2](https://github.com/erzod31/ManageYourLibrary/releases/tag/v0.5.3-native.2).
Build source: `bc7a647ebb26a7491d68dc69a523d805584b0c0b` (clean checkout).
Native build and publication: [Actions run 37431536468](https://github.com/erzod31/ManageYourLibrary/actions/runs/37431536468).

| Package | Bytes | SHA-256 |
| --- | ---: | --- |
| ManageYourLibrary-0.5.3-Linux-x64.tar.gz | 91772004 | `aa5277948b76dd8b7f075e00db9798e27a54386ec3ac5287a1176a05f398276c` |
| ManageYourLibrary-0.5.3-macOS-arm64.zip | 37725666 | `b39e31d79798c43f4202f2c5b8bb8c4f26131fa3e3963ff41d285949e3087543` |
| ManageYourLibrary-0.5.3-macOS-x64.zip | 40075379 | `06b96ac3de425603c434a1c86a89ca0dbf9153aa10f92b6c5c23bb638e309cb4` |

All 24 release assets were downloaded anonymously after publication; their
sizes and SHA-256 matched GitHub's digests. Each platform checksum file was
checked against those actual downloaded files. The build/OCR manifests, wheel
locks, frozen runtime/first-use reports and first-use instructions accompany
each application archive.

The post-download targeted privacy scan examined 2059 Linux payload files,
611 files in each Mac ZIP, six compiled entry scripts per target and 503/504/504
compiled modules respectively. It found no matches for the former private
Windows profile/name/repository markers or the tested credential/private-key
patterns. The 111 thin Mach-O binaries in each Mac package had no absolute
non-system dylib dependencies. This is a targeted audit, not a guarantee that
all possible sensitive information or security defects have been ruled out.

## Checks actually executed

- Ubuntu 22.04 x64, macOS 15.7.9 Apple Silicon and macOS 15.7.9 Intel each ran
  **409 unit tests, all passed, no skips**, on their own native runner.
- Each target passed source smoke and catalog performance gates, then frozen
  smoke, Tk initialization, bundled-language presence, real synthetic image OCR
  and PDFium-rendered PDF OCR.
- Each frozen GUI passed the five first-use checks: clean defaults, empty
  workspace, no background book operations, no automatic network requests and
  fresh state. The test blocks networking and uses an isolated temporary profile.
- Each final archive was extracted on its native runner and passed frozen smoke,
  runtime OCR/Tk/PDFium and the first-use checks again. Payload hashes matched
  before/after archiving; internal-only symlinks and executable bits were retained.
- Both macOS bundles passed `codesign --verify --deep --strict` before and after
  extraction. Finder-visible version/build metadata is 0.5.3 and bundle ID is
  `org.manageyourlibrary.desktop`.

The OCR inventory hashes describe the prepared native input runtime. PyInstaller
may relocate/re-sign native files afterwards; use the main build manifest's
`payload_sha256` map for final packaged bytes. Native wheel locks identify the
actual resolved Python dependencies for each architecture.

## Limitations

macOS has **ad-hoc signing only**, no Developer ID and no Apple notarization.
Gatekeeper/Finder opening after an Internet download has not been tested manually.
Linux targets desktop x86_64 with glibc 2.35; other distributions/architectures
are not certified. Automated macOS checks do not certify older macOS versions.
Manual installed-UI, upgrade and uninstall checks were not performed. SHA-256
and automated diagnostics do not constitute a security or usability certification.

Supplement 2 corrects the Finder version metadata in supplement 1. Earlier
assets/tags are retained, not overwritten. The Windows v0.5.3 assets and tag
remain unchanged and the original development repository remains private.
