# PDF converter 2.0 — validation results

## Supplied failing document

Input: INE090A08UC2(1)(1).pdf, 192 source pages.
SHA-256: 5473d83b158faf17a910112b623fd7bd2773b8de90f065ecc8252f61f577eb72

The previous converter stopped on page 1 because small vector outlines were classified as unsupported symbols.

New result: 290 A4 output pages, 191 source pages rebuilt, 120 table detections processed. Source page 138 (organisational chart) retains its original appearance and original fonts on output page 217. Overall status: PARTIAL_REVIEW_REQUIRED. All 77,582 extracted word spans on rebuilt pages, including their footers, were verified as Mulish 11pt. Original Wingdings star markers are retained as 11pt-high artwork and listed in the page reports. The original source file is unchanged.

Automated checks run for every rebuilt page: source character coverage, embedded font and size, horizontal/bottom bounds and same-line overlap. Positioned table rows also have exact character and ordered-digit checks. Ruled tables assign source tokens to detected cells and check their combined inventory; this does not prove semantic cell assignment for every malformed source table. Repeated headings can add text intentionally.

All 290 output pages were rendered for contact-sheet inspection. Detailed checks included the cover, definitions table, broken financial-table headers, dense equity-history tables, and preserved chart. Page-by-page mapping and any exceptions are in INE090A08UC2-corrected.pdf.json. Page boundaries from the source are retained, so some continuation pages contain little text. Dense tables may span multiple A4 landscape pages. Original internal page references remain unchanged; source-page bookmarks provide the mapping.

## Independent real-document regression

The original 230-page form20f.pdf was freshly converted to 447 output pages using its reviewed profile. Checks verified 8,873 original rows and 2,604 numeric rows; 82 repeated heading rows; contents page numbers and click targets; page orientation, margins, footers and embedded Mulish font sizes. Its two organisational charts retain original label fonts as documented by that profile.

## Automated suite

Command: PDF_FORM20F_RESULT=<fresh result.pdf> python -m unittest discover -s tests -v

29 test methods discovered: 19 passed, 10 skipped. Skipped tests require older original files that were not available locally or an older profile-specific handle-check fixture. They are NOT counted as passes. Historical converted sample PDFs bundled in testing/ are not evidence of fresh source conversion.

Coverage includes generated fixtures for:

- Plain prose, bold headings, A4 landscape and decorative page borders.
- Borderless numeric columns, ruled tables, merged cells and centred Unlimited/numeric values.
- Multi-page tables, wide nine-column tables and a cell taller than one page.
- Original vector diagrams, blank pages, scanned image-only pages and long unbreakable text.
- Rotated pages, unsupported Chinese glyphs and mixed supported/unsupported pages.
- Annotation appearance preservation with explicit flattening notice.
- Interactive forms, encrypted files and malformed files: blocked without overwriting an existing output.
- Strict mode: unsupported page fails without producing an output.
- Direct URL downloads, redirects, duplicate URLs, HTTP 404 and HTML responses.
- Continuing the batch after failed downloads, current-version resume and older-version reprocessing.
- Partial status, original-font page list and relative original/output links in the XLSX report.
- Native message framing and local queue retry after a simulated file-lock error.

Extension app.js and background.js passed Node syntax checks. Actual Windows installation and Chrome/Brave native messaging UI were not run in this Linux environment. No thousands-of-files load test was performed. The batch engine processes one PDF at a time, saves progress after each state change and refreshes Excel every ten files and at completion.

## Practical limits

This is not a universal guarantee for every PDF. Scans, unsupported scripts, unusual vector layouts and failed page checks become explicitly marked preserved pages, which retain original fonts. Editable forms and signed/password-protected documents are blocked. General reflow does not recreate interactive links or rewrite internal source-page references. Preserved annotation appearance is flattened; the unchanged original retains editable comments. Mulish 11pt is verified for rebuilt text, not for lettering embedded inside images or preserved artwork.

Review the PDF and the per-page JSON before publication. A partial conversion is a usable draft with named exceptions, not full font compliance.
