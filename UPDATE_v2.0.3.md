# Version 2.0.3 — vector header and top page numbers

The supplied original org.pdf has an outlined vector ICICI logo, rather than a bitmap image. It also places source page numbers 2–6 at the top centre. Earlier versions retained these numbers as body content and could preserve the first page with its old logo.

This release recognizes the reviewed vector-header region by a rendered fingerprint, and removes it before adding the reference banner. Unknown artwork is not automatically deleted. Top-centre source page numbers are removed only when the value matches its source page index and at least two pages share the same vertical placement. A single ambiguous number is retained. Ordinary body numbers are not removed. Recognized header/page-number cleanup also runs on pages that require original-layout preservation.

Fresh result from org.pdf: six A4 pages, all six source pages rebuilt, seven table detections processed, Mulish 11pt text, one replacement banner per page. Every output page was rendered and visually checked. Text coverage was checked after excluding the verified source page numbers and normalizing Symbol bullets. No original page-number row remains at the start of the content.

Regression suite: 36 methods discovered, 23 passed, 13 fixture-dependent skips. New tests cover repeated top-centre numbers and an ambiguous single-page number. Previous tests cover links, underlining, colour, bold classification, tables, partial outcomes and URL batches. Windows browser integration was not run in this environment.

Install from a new permanent folder, run INSTALL_EXTENSION_WINDOWS.bat and reload/load its extension folder in Chrome or Brave. Reprocess original PDFs. Resume rebuilds older-version results with existing downloaded originals. Do not use already converted files as inputs. Other constraints and preservation exceptions in UPDATE_v2.0.2.md remain applicable.
