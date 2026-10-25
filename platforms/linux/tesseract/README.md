# Linux Tesseract Runtime

Generated output only. Run `python3 tools/bundle_native_ocr.py` on Linux to build
the pinned PNG-only source profile. Do not copy a distro runtime into this folder.
The build and packaging validators require `native-ocr-manifest.json`, exact
sources, notices and model hashes; a binary alone is not accepted.

Expected layout:

```text
platforms/linux/tesseract/tesseract
platforms/linux/tesseract/tessdata/eng.traineddata
platforms/linux/tesseract/tessdata/spa.traineddata
platforms/linux/tesseract/tessdata/fra.traineddata
platforms/linux/tesseract/tessdata/chi_sim.traineddata
```

The source builder emits the first layout, plus `nld`, `osd`, license/source
directories and the inventory. The legacy alternative below is not a license
approval and is rejected unless it satisfies the same controlled inventory:

```text
platforms/linux/tesseract/bin/tesseract
platforms/linux/tesseract/share/tessdata/eng.traineddata
platforms/linux/tesseract/share/tessdata/spa.traineddata
platforms/linux/tesseract/share/tessdata/fra.traineddata
platforms/linux/tesseract/share/tessdata/chi_sim.traineddata
```

Release builds fail if this runtime is missing. For development-only builds that use a system `tesseract` from `PATH`, set `MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1`.
