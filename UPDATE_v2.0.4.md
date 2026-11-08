# Version 2.0.4 - Mulish italics and portrait pages

This release repairs the regression in the supplied 192-page INE090A08UC2 disclosure. Version 2.0.2's formatting protection kept an entire page in its original font when it contained italic text. Version 2.0.4 embeds real Mulish italic and bold-italic fonts, so those pages can now be rebuilt without removing their italic emphasis.

The general conversion engine now uses A4 portrait (210 x 297 mm), including its original-layout fallback. It no longer switches difficult tables to landscape automatically. Existing reviewed document profiles retain their documented orientation choices, including the Form 20-F profile's landscape financial tables.

## The supplied disclosure

- Body, footer, table and chart text is Mulish at 11pt, matching Word's size 11. This is not CSS 11px.
- All source pages are rebuilt in portrait. The reference banner/footer and custom margins remain: top 3cm, bottom 2.55cm, left 1.88cm, right 1.89cm. The top margin is measured from the paper edge, not as a 3cm gap below the banner.
- The seven dense equity-table pages are reconstructed as real tables. Numeric row relationships, negative adjustments, the footnoted share quantity and totals are checked. Rows stay together, and column headings repeat on new pages.
- The organisational chart is redrawn with Mulish 11pt labels while retaining its hierarchy, names and footnotes.
- The two widest borrowing tables are divided into two column sections. Series appears in both sections to identify the corresponding row. The first section holds Coupon, Tenor and Amount; the second holds Allotment, Redemption, Rating and Security. Every source cell is compared with the resulting panels.
- Original bold, italic, underline and hyperlink information is retained where present in the extracted source. Original Wingdings list markers remain small graphic symbols; they are reported separately and are not text in a substitute font.

These special layouts are enabled only for the exact reviewed source fingerprint. An unfamiliar complex chart or table can still be returned with PARTIAL_REVIEW_REQUIRED and original fonts rather than silently losing content. The Excel report and adjacent PDF JSON list any preserved pages. No claim is made that every arbitrary PDF can be reconstructed without review.

Validation result: 192 source pages became 284 A4 portrait pages, with no preserved original-font pages. All PDF text spans are Mulish at 11pt. Checks passed for 63 equity-table quantity/capital pairs, 264 borrowing-table cells, per-source-page text coverage, style coverage and hyperlink targets. All pages were rendered for visual review. The test suite discovered 41 methods: 28 passed and 13 unrelated fixture-dependent tests were skipped. The corrected PDF is also included in testing/.

## Update and reprocess

1. Close the old converter and its extension tab. Extract this ZIP into a new permanent folder.
2. Run INSTALL_EXTENSION_WINDOWS.bat from that folder.
3. In chrome://extensions or brave://extensions, remove the old unpacked copy and use Load unpacked to select this package's extension folder. Confirm version 2.0.4.
4. Open the extension, connect, select the existing batch and Resume. Results made by an earlier version are rebuilt from the downloaded originals. Alternatively, start a new batch with the PDF URLs.
5. Use original PDFs as inputs. Do not feed the already converted PDF back into the converter.

The standalone upload interface is also included: run START_WINDOWS.bat, confirm v2.0.4 in its title, and choose Add PDFs & convert.

URL downloading, separate batch folders, the Excel status report, file links and resume behavior remain included. Conversion and local HTTP download tests run on Linux; installation and the Chrome/Brave native-host connection have not been executed on Windows here.

## Fonts

The new Mulish-SemiBoldItalic and Mulish-BlackItalic fonts are static instances at weights 600 and 900 from Google Fonts' Mulish italic variable font:
https://github.com/google/fonts/blob/main/ofl/mulish/Mulish-Italic%5Bwght%5D.ttf

The existing body/emphasis weights are unchanged. All four fonts are covered by assets/OFL.txt.

See testing/v2.0.4-test-results.txt and testing/INE090A08UC2-v2.0.4-validation.json for the executed checks.
