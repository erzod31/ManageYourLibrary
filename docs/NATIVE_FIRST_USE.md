# macOS and Linux: first use / primer uso

These native packages include Python, Tk, PDFium and local Tesseract OCR with
English, Spanish, French, Dutch and simplified Chinese data. No app account,
API key, separate Python or Tesseract installation is required.

## macOS

Choose `arm64` for Apple Silicon (M1/M2/M3/M4 or later) or `x64` for Intel.
The automated checks run on macOS 15; older systems are not certified.
Extract the ZIP in Finder and drag `ManageYourLibrary.app` into Applications.
Open it, choose a writable library folder, and start with disposable book copies.

**This app has only an ad-hoc signature: no Developer ID or Apple notarization.**
Gatekeeper may block an Internet download. After checking the official download
and its SHA-256, use Apple's documented Privacy & Security / Open Anyway flow
only if you trust this release. Do not disable Gatekeeper globally. Managed Macs
may forbid unsigned applications; that requires a notarized future release.
See https://support.apple.com/en-us/102445.

## Linux

This package targets x86_64 desktop Linux; automated checks run on Ubuntu 22.04
(glibc 2.35). A graphical desktop and standard X11/Tk system libraries are
required. Other distributions and ARM devices are not certified by these tests.
Extract the **complete** `.tar.gz`, retaining `_internal` and executable bits:

```bash
tar -xzf ManageYourLibrary-0.5.3-Linux-x64.tar.gz
./ManageYourLibrary/ManageYourLibrary
```

The package is not an AppImage, `.deb` or `.rpm`; no installation script or sudo
is needed. Do not run from inside an archive or move just the launcher.

### Linux shared libraries: modification and evidence

For builds carrying `_internal/licenses/linux-system/source-asset.json`, obtain
the named `*-license-sources.tar` from the **same release** and verify its recorded
SHA-256. Keep it with the application archive. It contains exact Ubuntu source
archives, Debian patches/build recipes and provenance indexes; copyright and
referenced license texts also accompany the app. This evidence covers the listed
Ubuntu-owned files; Python, Tk, wheels and OCR have separate provenance.

For LGPL-covered libraries, the applicable license preserves modification and
reverse-engineering rights for debugging those modifications. See
[LGPL 2.1 sections 4 and 6](https://raw.githubusercontent.com/systemd/systemd/v249/LICENSE.LGPL2.1)
and, where applicable,
[LGPL 3 section 4](https://raw.githubusercontent.com/coreutils/gnulib/master/doc/COPYING.LESSERv3).
Retain copyright/license notices and the terms applicable to each component.

Close the app, keep the original archive untouched, and work on a complete copy
in a folder you own. Replace a library only with a compatible build for the same
architecture, preserving its SONAME, filenames, dependencies and symlinks. Use a
fresh disposable profile for testing, for example:

```bash
./ManageYourLibrary-test/ManageYourLibrary --profile "$PWD/myl-lgpl-test-profile"
```

To revert, close the modified copy and launch the untouched original bundle;
preserve your profiles and book backups separately.

Release checksums identify official bytes. Source inspection found no shared
library SHA allowlist in normal app startup; the
[PyInstaller 6.21 loader](https://raw.githubusercontent.com/pyinstaller/pyinstaller/v6.21.0/bootloader/src/pyi_utils_posix.c)
uses the bundle's library search path. **Modified-library loading has not yet
been validated on the new package.** The required native check must confirm which
modified copies actually load and repeat GUI/accessibility/OCR tests. Record
original/final hashes and any transformation's command, tool version and date;
an unexplained hash difference is not proof of a specific transformation.
Source delivery and these checks do not constitute global license approval.

## Safe first use

New profiles start empty. Choose a writable library folder; use Import for more
books. Confirming an import can move or rename originals: back up first.
Review uncertain identities; never assume matching titles mean the same edition.
Open uses the desktop's default PDF/EPUB reader, which must be installed separately.
Internet is optional for web metadata and covers; book OCR remains local.
Local AI is off by default and needs a separate optional engine/model.
Existing user profiles are preserved; this is not a factory reset.

## En español

Mac: elige `arm64` para Apple Silicon o `x64` para Intel, extrae el ZIP y copia
la app a Aplicaciones. No está notarizada por Apple: consulta el aviso anterior.
Linux: extrae todo el `.tar.gz` y ejecuta `ManageYourLibrary/ManageYourLibrary`;
necesitas un escritorio gráfico Linux x64 compatible.
En ambos casos no necesitas instalar Python ni Tesseract. Elige tu carpeta de
biblioteca, haz copia de seguridad y prueba Importar con copias de pocos libros.

The release includes per-platform SHA-256 checksums, exact source/build manifests,
native wheel hash locks and frozen diagnostic reports. Automated checks include
Tk initialization, local image/PDF OCR and an empty first-use GUI with networking
blocked. Manual Finder/Gatekeeper opening, installed-UI, upgrades and uninstallation
have **not** been tested. Hashes identify the published bytes, not a security
certification. Third-party OCR licenses are inside the bundled runtime.
