# A4 PDF Converter 2.1.0

Convert original PDFs locally to the reference banner/footer, A4 portrait and Mulish 11pt. Includes a Windows desktop uploader and a Chrome/Brave extension for PDF URL batches.

[Download the complete v2.1.0 package](dist/A4_PDF_Converter_Extension_v2.1.0.zip?raw=true). Source code, extension files and installer are also available directly in this repository.

## Install or update

1. Close the converter and all Chrome/Brave windows so an old native helper cannot remain running.
2. Extract this complete ZIP into a new permanent folder. Keep its files together.
3. Run **INSTALL_EXTENSION_WINDOWS.bat**. Python 3.11 or 3.12 with Add Python to PATH is required. The first installation downloads the listed dependencies.
4. Open `chrome://extensions` or `brave://extensions`, enable Developer mode, remove the old unpacked copy, and Load unpacked using this package's **extension** folder.
5. Open PDF Batch Converter and click **Connect / refresh batches**. It must say **Extension and local converter 2.1.0 connected**. A version mismatch blocks conversion and gives update instructions.
6. Paste direct PDF URLs or import a text list, then choose Download & convert. To rebuild an old batch, select it and Resume; previous-version results are regenerated from the downloaded originals.

For local PDF uploads, run **START_WINDOWS.bat**, confirm v2.1.0 in the title and choose **Add PDFs & convert**. Add folder and Watch folder are also available.

Use the original PDF as input. Previously generated converter outputs are rejected to prevent duplicate headers and repeated reflow.

## Output settings

- A4 portrait: 210 x 297 mm.
- Body and footer: embedded Mulish **11pt**, matching size 11 in Word.
- Existing regular/emphasised distinction uses Mulish SemiBold/Black, with matching italic fonts. Original bold, italic, underline, strikethrough, colour and URL links are retained on rebuilt text.
- Top page margin 3cm, bottom 2.55cm, left 1.88cm, right 1.89cm. The top margin starts at the paper edge; it is not a 3cm gap below the banner.
- Reference banner and right-aligned Page x | total footer.
- Reflow may change wrapping and page count. Original written page references remain; source-page bookmarks map to the output. The separate legacy Form 20-F profile also updates its reviewed contents links.

## What changed in 2.1.0

- Inspects embedded font programs when a PDF uses opaque aliases such as CIDFont+F8. This recovers the actual font weight/style and symbol identity instead of treating a normal bullet as an unsupported alphabet character.
- Normalises recognised Symbol bullets and retains other recognised symbol glyphs as explicitly reported 11pt-high artwork.
- Recognises the reference ICICI banner after resizing or JPEG recompression, with conservative visual matching. Unknown images are retained for review.
- Removes repeated top/bottom source page numbers, including from pages requiring preservation.
- Reconstructs enumerated contents lists with a separate page-reference column and keeps hanging bullet/list indents.
- Verifies text and number order inside individual rendered table cells, including split rows and superscript footnotes. Keeps filled backgrounds separate from thin border strips.
- Excludes invisible white background patches from table detection, preventing prose from acquiring invented table borders.
- Checks text coverage, styles, links, bounds and overlap during reflow; then measures fonts and page dimensions again from the saved PDF.
- Gives each output a readable HTML checks report, a detailed JSON report, and an explicit compliant/partial outcome. Version-aware retry/resume and engine/extension version checks prevent stale results.

These font, symbol, contents-list, matching and verification changes are general rules. They do not depend on this document's filename or hash. Older reviewed layout profiles remain available for their supported complex documents.

## URL batches and reports

Each batch is saved under `Documents\PDF_URL_Conversions\Batch_<date>_<id>`:

- **originals/**: downloaded originals.
- **converted/**: results passing the final measured format gate.
- **review/**: incomplete results, preserved pages, unverified artwork or other format exceptions. These are not included in the successful-conversion count.
- **conversion_status.xlsx**: each requested URL, download/conversion status, original/output links, page counts, font compliance, review reasons and a link to the HTML checks report.
- **batch.json**: resume state.

The extension's **Checks** button opens the report for that PDF. **Retry failures / review** retries partial results as well as failures. Originals remain available in every successful download. One failed PDF does not stop the queue.

Keep the browser open during a batch; the extension tab may close. Pause after current PDF, then resume later even after a browser restart. Excel updates every 10 jobs and at completion/pause; close Excel before refreshing it. Keep the report beside its folders so file links continue to work.

The desktop uploader writes PDFs, matching checks reports and batch_report.csv. Partial results are placed in its review/ subfolder. Its SQLite history supports skipping completed jobs and resuming interrupted batches.

## Limits and honest outcomes

A PDF is a drawing format, and may not contain reliable paragraph, table or character information. A successful font/page check is not a guarantee of perfect semantic reconstruction of every possible document. Review complex layouts before publication.

Scans, unsupported scripts/glyphs, unfamiliar diagrams, ambiguous layouts and unverified text inside images may need OCR or manual/source-document editing. The converter reports these cases; it does not invent missing text. Unknown artwork is not automatically deleted. Password-protected files need an unlocked original; signed or interactive forms are blocked to avoid silently losing fields or signatures.

The older Form 20-F profile still has two original-font charts and some landscape financial tables. The new final gate correctly sends that result to review/ rather than counting it as fully format-compliant.

PDFs are processed locally. No paid API or document-upload service is used. Public HTTP(S) URLs are supported; browser login cookies are not copied. The batch limit is 20,000 URLs and 300 MB per PDF.

## Command line

```text
python converter.py input.pdf output.pdf
python converter.py input.pdf output.pdf --strict
python batch.py input_folder output_folder
python batch.py input_folder output_folder --watch
```

Strict mode rejects any partial/noncompliant conversion without overwriting the existing destination. The normal mode keeps an explicit review result for troubleshooting.

## Validation and support files

See **UPDATE_v2.1.0.md** and **testing/v2.1.0-validation.json** for the exact tested documents, outcomes and known exceptions. Test execution is recorded in **testing/v2.1.0-test-results.txt**. The corrected current PDF and its reports are in **examples/**.

Conversion, URL download/redirect/error handling, Excel links, resume and version guards are tested on Linux. Actual Chrome/Brave native messaging installation has not been run on a Windows PC here. Enterprise browser policy can block unpacked extensions or native hosts.

The fonts are distributed under assets/OFL.txt. The reference header is the user's supplied asset. Dependency licenses apply, including PyMuPDF's AGPL/commercial licensing.
