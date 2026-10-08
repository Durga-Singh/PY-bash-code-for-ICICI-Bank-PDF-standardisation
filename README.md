# Production release

Extract this ZIP into a NEW folder, close the old app, and run START_WINDOWS.bat. The title bar must say A4 PDF Converter v1.4. Select original PDFs using Add PDFs & convert. Successful results from earlier versions are regenerated with this new profile.

Fixes for the reported layout issue:
- The complete Form 20-F opening page fits on ONE portrait A4 page at 11pt.
- Landscape pages now have a full-width banner; the logo is not stretched. The remaining report pages retain landscape to fit the financial columns. Total: 494 pages.
- The two original charts retain their original label fonts, as previously disclosed.

New tested inputs, all A4 portrait, Mulish 11pt, with the reference header/footer and custom margins:
- Money2India Canada new-customer offer: 2 pages. Old logo and orange outer border removed.
- Seniors Advantage GIC terms: 2 pages. Benefit table retained on one page. Verified duplicate raster text overlays removed; underlying text rebuilt in Mulish. Paragraphs inside the benefit cell and bullet lists retained.
- Hello Canada/RBC referral program: 3 pages. Lettered conditions and FAQ numbering retained.

Validation: seven regression tests passed, including all new documents, prior logo/border samples, annual-report row checks, Windows-style file cleanup, and retry/resume. Font sizes, content inventory and table numeric sequence checks passed. All seven new-document pages were rendered and inspected, along with the corrected annual-report cover and header. Windows GUI execution itself is not available in the Linux test environment.

Known limitation: the annual-report profile recognizes the supplied report by content fingerprint; arbitrary complex PDFs may still require a separate profile. No claim of universal lossless PDF reconstruction.

---

# A4 PDF converter — sample-tested reflow profile

## Start on Windows
1. Install Python 3.11 or 3.12 with **Add Python to PATH** selected (including Tcl/Tk).
2. Extract the complete ZIP to a folder. Do not run it inside the ZIP.
3. Double-click **START_WINDOWS.bat**. First setup downloads the Python dependencies.
4. Click **Add PDFs & convert** to select one or many files. They convert automatically.
5. **Add folder** queues PDFs recursively. **Watch folder** processes new/changed PDFs after they stop changing for three seconds. Leave the app open to continue watching.
6. Open the output folder for PDFs, validation JSON files, and **batch_report.csv**.

Documents are processed locally. No document upload to a remote service is required. Dependencies are downloaded during initial installation only.

## Exact settings used
- A4 portrait: 210 × 297 mm.
- Mulish SemiBold body / Black emphasis, preserving the sample's weight distinction.
- Body and footer: **11pt**, matching size 11 in Microsoft Word. The font is embedded in the PDF.
- Banner image extracted from the provided reference, with the same approximately 22.81mm visible height.
- **Top margin: 30.00mm from the top edge of the page to the content boundary.**
- Left 18.8mm, right 18.9mm, bottom content boundary 25.5mm.
- Footer follows the reference's right-aligned blue spaced `Page` label and dark `x | total`, redrawn in Mulish at the requested size. Counts reflect the new pagination.

The screenshot's Last Custom Setting is applied: top 3cm, bottom 2.55cm, left 1.88cm, right 1.89cm. The banner sits inside the top margin, leaving approximately 7.2mm between its bottom and the content boundary. The bottom setting is a minimum clear margin, not a requirement to stretch text to that position.

## Layout and checks
PDFs store positioned drawing instructions, not reliable Word/Excel paragraph/table structures. To increase text size without overlapping table cells, this tool reconstructs recognized ruled tables and reflows text. Wrapping, row heights and page counts change. The tested legacy-logo and page-border documents flow continuously to avoid mostly empty pages; other profiles retain original page breaks. Tables can continue across additional pages, repeating detected headings. Key/value tables do not repeat their first data row. It is not a pixel-identical conversion.

The included sample is based on the supplied financial-results PDF. Treat the tool as a tested profile for comparable text-based, ruled-table PDFs, not a universal lossless PDF converter. Review the sample and a representative selection of each new layout before processing a collection. Editable Word/Excel sources are preferable if exact source structure must be retained.

Checks include visible text character inventory, embedded font glyph coverage, A4 dimensions, font sizes, content bounds, top margin, and numeric table-row sequence checks. Passing automated checks does not prove every semantic relationship or visual detail is correct. Output status intentionally remains **CONVERTED_REVIEW_LAYOUT**.

Scans/empty pages, encrypted PDFs, interactive forms, rotated pages, unsupported graphics, extraction mismatches and failures are marked **NEEDS_REVIEW**. Such files are not silently rasterized or shrunk. OCR and general unruled/multicolumn document reconstruction are not supported. Existing PDF links, bookmarks, accessibility tags, signatures, metadata and forms are not retained in reconstructed output. Signed/interactive documents should be handled from their editable source.

## Long batches and resuming
- Files run one at a time; one failure does not stop the queue.
- Originals are unchanged. Output names include a hash to avoid filename collisions.
- Conversion history is stored in the output folder. Re-adding the same unchanged files skips successfully converted jobs. Failed jobs are retried when you select them again. Keep this folder to retain history.
- If the app closes, add the input folder again to resume. PDFs left partially written by interruption are reprocessed because their successful history entry was not committed.
- Keep the computer awake and the app open for unattended batches.
- Close `batch_report.csv` in Excel during conversion so it can be refreshed.

## Command line
After installation:
```
.venv\Scripts\python.exe batch.py "C:\Input PDFs" "C:\Converted PDFs"
.venv\Scripts\python.exe batch.py "C:\Input PDFs" "C:\Converted PDFs" --watch
.venv\Scripts\python.exe batch.py "C:\Input PDFs" "C:\Converted PDFs" --retry
```
Single file:
```
.venv\Scripts\python.exe converter.py "input.pdf" "converted.pdf"
```
macOS/Linux: create a virtual environment, install requirements, then use `python app.py` or `python batch.py`. Tkinter may need installation through the operating system.

## Assets and dependencies
The header is from your reference PDF. Mulish fonts are static instances of the Google Fonts Mulish variable font, distributed under the included SIL Open Font License. Dependencies have their own licenses; PyMuPDF is offered under AGPL/commercial licensing. Review dependency licensing before integrating this into a distributed or proprietary application.

## Validation of this delivered version
The 11-page supplied sample produces 19 pages. All 11 recognized tables and 193 numeric row sequences were checked; no numeric rows were lost, added, or reordered within a row. All output pages were rendered and visually reviewed. Measured content bounds start 30.00mm below the page edge; body font sizes are 11pt. Batch conversion, resume skipping and unsupported-file reporting were exercised. Python modules compile successfully. The desktop GUI and Windows launcher could not be launched in the headless Linux test environment and require a first-run check on your computer.

## v1.1 Windows file-lock fix
Temporary PDFs are now explicitly closed before their temporary folder is removed, including when conversion raises an error. Source and validation PDFs are also closed before returning. Failed history entries are retried on selection, including failures recorded by the earlier version; no history deletion is needed. Successfully converted files are still skipped. Regression checks cover successful conversion, cleanup during exceptions, retry of an earlier failure, and skipping a completed job. These checks simulate Windows locking requirements on Linux; native Windows execution has not been verified here.

## v1.2: previous release
Close the old app, extract this ZIP into a new folder, and run START_WINDOWS.bat there. The title bar must say **A4 PDF Converter v1.2**. Failed conversions can be selected again without deleting conversion history.

New supported cleanup: pixel-matched recognition of the legacy ICICI logo supplied in INE090A08KY7.pdf, including its surrounding frame; outer rectangular page borders; preservation of colored text and underlined footnote references. Unknown images are not classified as ICICI logos by filename. Font size and margins remain the agreed 11pt/A4/3cm top/2.55cm bottom/1.88cm left/1.89cm right.

Test outcomes:
- INE090A08KY7.pdf: 3 input pages -> 3 output pages; 1 old header removed; 4 tables retained; 3 decimal-number row sequences verified.
- dctoc.pdf: 17 input pages -> 17 output pages; 16 outer borders removed; visible text inventory checked.
- form20f.pdf: all 230 pages inspected for layout features. Strict conversion is unsupported: checkboxes on page 1, organisational diagrams on pages 27 and 59, financial tables without full grids (example page 28), and private Symbol-font glyphs on pages 146, 151 and 195. This was reported as NEEDS_REVIEW in v1.2. The v1.3 exception profile below now supports the exact supplied file.

This remains a converter for supported layouts, not a universal lossless PDF engine.

## v1.3: previous release — Form 20-F conversion

Close the old app, extract this ZIP into a new folder, and run START_WINDOWS.bat. The title must say **A4 PDF Converter v1.3**. Add PDFs as before; the supplied Form 20-F is recognized automatically by its file contents, even if renamed.

This new profile converts the exact supplied 230-page `form20f.pdf` into 496 A4 landscape pages. All rebuilt body, table and footer text is embedded Mulish 11pt. Landscape provides room for the financial columns. Text and values remain in their source rows and columns; complete row contents stay together. Long tables continue across pages, with detected year-based column headings repeated. The original reference banner retains its aspect ratio and original portrait-page width on the wider landscape page.

**Explicit exceptions:** organisational charts on source pages 27 and 59 are retained as original vector artwork, including their original label fonts. They are not Mulish 11pt. Eight private Symbol-font dash glyphs were visually checked and mapped to a Mulish em dash. The original page references in the text/contents remain unchanged; the Source page footer and bookmarks identify the original page on each converted page. Italic styling is not retained by the bundled two-weight font family.

Validation: 8873 source rows checked individually; ordered numeric sequences checked for each row; exact character inventory checked with documented page-footer/dash/repeated-heading normalization; no rebuilt word overlaps; A4 dimensions and horizontal bounds checked. 88 heading rows repeat on continuation pages. Two preserved chart regions are listed separately in the validation JSON.

The profile is limited to the exact supplied report because its diagram regions and Symbol-font meanings were reviewed. It does not treat arbitrary annual reports as safe automatically. Other files still use the existing supported-layout converter and may return NEEDS_REVIEW. The GUI/launcher remains untested on native Windows; file-handle cleanup is covered by regression checks.
