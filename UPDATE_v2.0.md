# Version 2.0 — verified page-level conversion

Close the old app and browser first. Extract this package into a new permanent folder, run INSTALL_EXTENSION_WINDOWS.bat, and load its extension folder from chrome://extensions or brave://extensions. Remove the previous unpacked copy if the browser lists two copies. The stable extension key is unchanged. Reconnect and Resume an existing batch: version 1.9 outputs are rebuilt; downloaded originals are reused. Keep old output folders until you have reviewed the new results.

For local PDFs, run START_WINDOWS.bat and add your originals. Re-add files processed with older versions to rebuild them. Python 3.11 or 3.12 is required. See EXTENSION_SETUP.md for installation.

## What changed

Previously, one unsupported vector on a page stopped the whole file. The new engine works page by page, reconstructs ruled and borderless tables, retains merged-cell alignment, handles broken table borders, and tries A4 landscape when columns cannot fit safely in portrait at 11pt. Dense borderless tables use landscape and repeat detected bold column headings. Long cells can continue across pages without reducing text size. Rebuilt text is checked for missing characters, font, size, margins and overlap; borderless rows also have ordered numeric checks.

Existing reviewed document-specific profiles remain available. Unknown artwork, scans and unsupported scripts retain their original page appearance. This is a deliberate partial conversion, not a claim that their text became Mulish. Editable forms, signed PDFs and locked PDFs are blocked. Originals are never overwritten.

## Statuses and files

- CONVERTED_REVIEW_LAYOUT: rebuilt pages passed automated checks; visually review before publishing. Artwork exceptions are listed in the JSON report.
- PARTIAL_REVIEW_REQUIRED: one or more source pages retain original layout and original fonts. The Excel report names those source pages and reports font compliance separately.
- Failed: download, password, interactive form, signature, malformed PDF or another file-level error prevented conversion. The next URL still runs.

Every converted PDF has a JSON report with source-to-output page mapping, reasons for preserved pages, and exceptions. PDF bookmarks locate source pages after pagination changes. Original internal page references are not rewritten by the general engine. Interactive links in rebuilt pages are not recreated; originals retain them. On preserved annotated pages, visible annotation appearance is flattened; editable comments remain in the original file.

Batch folders contain originals/, converted/, conversion_status.xlsx and batch.json. Excel links each input to its output and records partial conversions. Resume skips completed current-version results and rebuilds older versions. This extension uses a local Python helper; it is not a standalone Web Store extension.

## Format

Mulish 11pt for rebuilt body, tables and footer (Word size 11, not CSS 11px). A4 portrait or landscape where needed. Reference header/footer. Top margin 3cm from page edge, bottom 2.55cm, left 1.88cm, right 1.89cm. Images and preserved source pages can retain original text fonts. No universal PDF reconstruction guarantee is made.

Testing was performed on Linux. The Windows installer and Chrome/Brave native-host connection still require verification on the target PC. The package includes automated tests and VALIDATION_v2.0.md with actual results and limitations.
