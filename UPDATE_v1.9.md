# v1.9 — Form 20-F layout repair

## Install this update

1. Pause the current batch and close the PDF converter browser tab. Disable the old extension in `chrome://extensions` or `brave://extensions` to stop its helper.
2. Extract this ZIP to a permanent folder. Run **INSTALL_EXTENSION_WINDOWS.bat** from the new folder.
3. Remove the old unpacked extension entry, then choose **Load unpacked** and select the new **extension** subfolder. The extension ID is unchanged.
4. Open the extension, select your existing batch and click **Resume**. v1.9 reprocesses successful results made by older converter versions using the saved originals. It skips files already converted by v1.9. Use **Retry failures** for failed entries.

Existing batch folders stay under Documents/PDF_URL_Conversions. No need to download the originals again when they are still there. Close Excel before the batch refreshes its report.

## Form 20-F changes

- Portrait A4 is the default. A4 landscape is used for dense financial tables (five or more numeric columns, or insufficient minimum column width) to preserve readable columns at 11pt.
- The supplied 230-page source now produces **447 pages: 348 portrait and 99 landscape**. Forty source pages contain dense tables requiring landscape; their continuations account for the 99 output pages.
- Contents leaders are drawn consistently, page numbers are updated to converted page numbers, and each contents entry is clickable. A continuation contents page repeats its heading.
- Prose paragraphs wrap together instead of preserving every old line ending.
- Numeric columns retain their source alignment while cell widths are adjusted without reducing the font.
- The extra “Source page” footer is removed. Source-to-output mapping is retained in PDF bookmarks and the JSON report.
- Rebuilt body and footer text uses embedded Mulish at **11 points**, matching Word size 11. The two original organisational charts retain their original lettering and vectors, as previously allowed for complex artwork.

Internal references in the body still use the original report's page labels; the PDF's Source page bookmarks provide that mapping. This change updates the front contents page; it does not rewrite every embedded cross-reference or the report's financial-statement index. Source page boundaries are retained, so some continuation pages have spare space. The output is reflowed and will not have the original page count.

## Verification

All 8,873 source rows were accounted for before prose/contents grouping. Content inventory, ordered digits within rendered rows, text overlap, horizontal and bottom margins, actual Mulish font size, footer numbering and all contents destinations were checked. All 447 pages were rendered to contact sheets; representative contents, prose, chart and dense table pages were inspected at readable size. The tested result is included under `testing/form20f-converted.pdf`.

Three document regression tests and three extension/backend tests passed. The extension tests include reprocessing a batch entry marked as v1.8, preserving downloads, and skipping current-version successes. Python compilation and JavaScript syntax checks passed. Actual installation on Windows/Brave has not been run in this Linux environment.

The repair is for the fingerprinted supplied Form 20-F. Other conversion profiles remain unchanged. Results continue to be labelled CONVERTED_REVIEW_LAYOUT for review before publication.
