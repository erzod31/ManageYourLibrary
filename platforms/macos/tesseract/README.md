# macOS Tesseract Runtime

Put the native macOS Tesseract runtime here before building a release.

Expected layout:

```text
platforms/macos/tesseract/tesseract
platforms/macos/tesseract/tessdata/eng.traineddata
platforms/macos/tesseract/tessdata/spa.traineddata
platforms/macos/tesseract/tessdata/fra.traineddata
platforms/macos/tesseract/tessdata/chi_sim.traineddata
```

This layout is also accepted:

```text
platforms/macos/tesseract/bin/tesseract
platforms/macos/tesseract/share/tessdata/eng.traineddata
platforms/macos/tesseract/share/tessdata/spa.traineddata
platforms/macos/tesseract/share/tessdata/fra.traineddata
platforms/macos/tesseract/share/tessdata/chi_sim.traineddata
```

Release builds fail if this runtime is missing. For development-only builds that use a system `tesseract` from `PATH`, set `MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1`.
