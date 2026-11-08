# Version 2.0.2 — retain text decoration and links

Use original input PDFs when rerunning. Resume now rebuilds results made by earlier versions.

This update detects underlines and strikethrough drawn as PDF vector rules, excludes connected table-grid edges, and carries the detected decoration into reflowed paragraphs and cells. Original text colours, bold classification and superscript markup are retained through the shared text formatter. URI links are associated with their source text and recreated as clickable links; URI targets are verified after fragment rendering. Links are not automatically underlined or recoloured unless the source has that styling. No new links are inferred from plain address text.

The supplied website notice was regenerated into two A4 pages. Its underlined title and two underlined web addresses match the original underlined text; both original clickable URL destinations match exactly. No Black font was introduced, and the old Canada logo remains removed. Both pages were rendered and inspected, including the meetings table.

Original italic text currently triggers explicit page preservation because the package does not include a verified Mulish italic face. Such pages retain original fonts and are marked PARTIAL_REVIEW_REQUIRED. Internal-link pages also retain original layout, with page destinations mapped to the new pagination. Special PDF link actions other than URI or internal page jumps are blocked rather than silently removed. These fallbacks are not full Mulish font compliance.

Automated regression: 34 methods, 21 passed, 13 fixture-dependent skips. Added tests verify rendered underlines, strikeout, colour, a URL containing query parameters, internal page-link remapping and italic preservation. The source notice's underlined tokens and clickable URI sets were compared directly with the output. Windows browser UI execution was not available.

Install: close old helper/browser, extract to a new permanent folder, run INSTALL_EXTENSION_WINDOWS.bat, and load the extension subfolder in Chrome/Brave. Resume the batch to reprocess older outputs using their original downloads. See EXTENSION_SETUP.md for details.
