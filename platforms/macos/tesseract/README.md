# macOS Tesseract Runtime

Generated output only. Run `python3 tools/bundle_native_ocr.py` on macOS to build
the pinned PNG-only source profile. Do not copy a Homebrew runtime into this folder.
The build and packaging validators require `native-ocr-manifest.json`, exact
sources, notices and model hashes; a binary alone is not accepted.

Expected layout:

```text
platforms/macos/tesseract/tesseract
platforms/macos/tesseract/tessdata/eng.traineddata
platforms/macos/tesseract/tessdata/spa.traineddata
platforms/macos/tesseract/tessdata/fra.traineddata
platforms/macos/tesseract/tessdata/chi_sim.traineddata
```

The source builder emits the first layout, plus `nld`, `osd`, license/source
directories and the inventory. The legacy alternative below is not a license
approval and is rejected unless it satisfies the same controlled inventory:

```text
platforms/macos/tesseract/bin/tesseract
platforms/macos/tesseract/share/tessdata/eng.traineddata
platforms/macos/tesseract/share/tessdata/spa.traineddata
platforms/macos/tesseract/share/tessdata/fra.traineddata
platforms/macos/tesseract/share/tessdata/chi_sim.traineddata
```

Release builds fail if this runtime is missing. For development-only builds that use a system `tesseract` from `PATH`, set `MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1`.
