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
