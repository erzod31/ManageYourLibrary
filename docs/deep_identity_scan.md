# Deep Identity Scan

Deep Identity Scan is the shared evidence layer used when normal metadata is
not enough to identify a book safely.

It does not replace the existing metadata flow. It adds a conservative
cross-check over short local signals:

- internal metadata;
- OPF/EXTH/PDF metadata already extracted by the app;
- filename candidates;
- first-page/front-matter candidates;
- valid ISBNs;
- selective OCR hints when OCR was already needed;
- short external bibliographic candidates returned by allowed providers.

The output is a decision:

- `AUTO_RENAME`: confidence is 90 or higher and there are no strong conflicts.
- `QUICK_REVIEW`: confidence is 75 to 89.
- `REVIEW_AGAIN`: confidence is 50 to 74.
- `UNIDENTIFIED`: confidence is below 50.

Only `AUTO_RENAME` can be used by the app to rename automatically, and the app
still requires a valid title and author after its existing safety checks.

## Privacy And Copyright

Deep Identity Scan does not store full book text, chapters, pages, or long OCR
output. It works with short metadata-like evidence only.

External bibliographic validation is limited to minimal candidate data such as
ISBN, title, author, and year. Full pages, OCR text, or document content are not
sent to external APIs.

OCR remains local and uses Tesseract. Cloud OCR is not used.

## Formats

EPUB:

- uses OPF/internal metadata first;
- uses front matter only when useful;
- does not use OCR unless the existing flow already needed selective cover OCR.

MOBI/AZW/AZW3:

- treats Kindle files as reflowable ebook formats, not as PDFs;
- reuses EXTH/header metadata already extracted by the app;
- can add front-matter evidence when available;
- never attempts to break DRM.

PDF:

- classifies PDFs as textual, scanned, mixed, protected, corrupt, or unknown;
- prefers embedded text;
- uses OCR only through the existing selective local OCR flow;
- corrupt or protected files remain conservative and go to review.

Images:

- use local OCR as a possible cover/page signal;
- OCR quality is penalized when text is weak or noisy.

Comic archives:

- supports readable CBZ/CBR-style archives as cover/image containers;
- can recover cover images from ZIP-backed archives and, when available locally,
  RAR-backed archives exposed through a `tar`/libarchive-compatible reader;
- uses internal archive folder/file names only as short metadata hints;
- never treats raw binary archive bytes as text evidence;
- remains conservative when no readable cover image or reliable metadata hint is
  available.

## Scoring

Strong evidence includes valid ISBNs, agreement between title and author from
multiple independent sources, structured metadata, and external candidates that
confirm the same short identity.

Weak or negative evidence includes index/chapter/prologue headings, publisher or
collection labels, filename-only guesses, poor OCR, and contradictory sources.

If confidence is insufficient, the app keeps the filename and sends the item to
review instead of inventing metadata.
