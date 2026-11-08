# Version 2.1.0 - general font decoding and verified output

The recurring failure in the supplied business-conduct PDF came from opaque PDF font aliases. The source embeds Mulish, Symbol and other fonts under names such as CIDFont+F8. The old engine did not inspect the embedded font metadata, so it missed bold/italic styles and did not recognise the bullet font. Unsupported bullets triggered whole-page preservation, which retained smaller original fonts and old page numbers. An image-hash-only logo check also missed the resized cover banner. The contents list was treated as prose instead of separate columns.

Version 2.1.0 fixes those causes in shared conversion code. It does not add a fingerprint-based layout profile for this PDF. The implementation also adds per-cell text/numeric checks, style checks, a final saved-file format gate, separate review output, clickable HTML checks reports and an extension/helper version handshake. Invisible white background patches are excluded from table detection, preventing invented table borders around prose.

The supplied 34-page code of business conduct now produces 34 A4 portrait pages. All actual text spans are Mulish 11pt. All source pages are rebuilt. The extra cover logo and source page numbers are removed; the replacement reference banner/footer is retained. Contents entries keep a separate page-reference column, bullets retain hanging indents, and the disciplinary-authority table is compared cell-by-cell. Bold and italic text are recovered from embedded font metadata.

The 192-page disclosure was also regenerated with this release: 285 A4 portrait pages, no preserved source pages and Mulish 11pt throughout the text layer. Its 63 equity-table row pairs and 264 borrowing-table cells were rechecked. Original symbol markers remain explicitly reported artwork. The consumer-education and bank-notice samples also pass the final measured format gate.

The 230-page Form 20-F profile was exercised as an exception case. Its original chart lettering and landscape financial tables remain documented limitations; this release identifies those output pages and labels the result PARTIAL_REVIEW_REQUIRED. It is not counted as a compliant conversion.

Use the new package's installer and extension together. Close the old app and browser first. The connection message must show version 2.1.0 for both extension and local converter. Resume rebuilds prior-version batches from downloaded originals; use Retry failures / review for partial results already made by the current version.

The corrected current PDF, its checks report and JSON are included in examples/. The final test log and document-level validation results are included in testing/. Windows browser installation still needs verification on the user's PC.
