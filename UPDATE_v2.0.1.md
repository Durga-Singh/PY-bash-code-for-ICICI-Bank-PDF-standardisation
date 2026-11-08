# Version 2.0.1 — font weight and Canada header correction

The supplied notice uses Mulish SemiBold for all visible text, but marks those spans with the PDF bold flag. The converter incorrectly promoted them to Mulish Black. Explicit Regular, Normal, Medium, Light, Book, SemiBold and DemiBold font names now take precedence over that flag. Explicit Bold/Black and unknown-face bold flags remain supported. This keeps this notice's original SemiBold weight, without adding bold headings that were not present in its source.

The reviewed ICICI Canada logo in website-content-bank-notice.pdf is now recognized and removed before adding the reference banner. Only reviewed image fingerprints are removed; arbitrary top-of-page artwork is not deleted.

Corrected notice: two A4 pages, all extracted text Mulish 11pt, no Mulish Black spans, exactly one replacement banner per page, original meeting values retained. Both pages rendered and visually reviewed.

Regression run: 31 methods discovered, 18 passed, 13 fixture-dependent tests skipped. New tests cover misleading SemiBold flags and mixed normal/bold rendering. Full test log in testing/v2.0.1-test-results.txt. No new Windows browser UI test was performed.

Upgrade: close the old helper/browser, extract to a new permanent folder, run INSTALL_EXTENSION_WINDOWS.bat and load/reload the extension folder in Chrome or Brave. Resume reprocesses previous-version results using the unchanged original downloads. Always reprocess originals, not already over-bold converted PDFs: the latter cannot reliably reveal the original font weights.

See UPDATE_v2.0.md and EXTENSION_SETUP.md for other setup instructions and limitations.
