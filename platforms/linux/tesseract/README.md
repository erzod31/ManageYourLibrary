# Linux Tesseract Runtime

Put the native Linux Tesseract runtime here before building a release.

Expected layout:

```text
platforms/linux/tesseract/tesseract
platforms/linux/tesseract/tessdata/eng.traineddata
platforms/linux/tesseract/tessdata/spa.traineddata
platforms/linux/tesseract/tessdata/fra.traineddata
platforms/linux/tesseract/tessdata/chi_sim.traineddata
```

This layout is also accepted:

```text
platforms/linux/tesseract/bin/tesseract
platforms/linux/tesseract/share/tessdata/eng.traineddata
platforms/linux/tesseract/share/tessdata/spa.traineddata
platforms/linux/tesseract/share/tessdata/fra.traineddata
platforms/linux/tesseract/share/tessdata/chi_sim.traineddata
```

Release builds fail if this runtime is missing. For development-only builds that use a system `tesseract` from `PATH`, set `MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1`.
