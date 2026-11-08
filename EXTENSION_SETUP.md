See **UPDATE_v2.1.0.md** when upgrading from an earlier release.

# PDF Batch Converter — Windows extension, v2.1.0

## Install once

1. Extract the ZIP to a permanent folder, for example `Documents\PDF_Converter`. Do not run files inside the ZIP.
2. Install Python 3.11 or 3.12 from https://www.python.org/downloads/windows/ if needed. Enable **Add Python to PATH**.
3. Double-click **INSTALL_EXTENSION_WINDOWS.bat**. Internet is needed for the first installation. No administrator account is required.
4. Open `chrome://extensions` in Chrome, or `brave://extensions` in Brave. Turn on **Developer mode**, choose **Load unpacked**, and select the **extension** subfolder from this package.
5. Click the extension icon to open PDF Batch Converter. Click **Connect / refresh batches**. If you move the package later, rerun the installer and reload the extension.

This is an unpacked extension, not a Chrome Web Store release. The local Python helper performs the conversion. Windows installation and browser integration must be verified on your PC; development tests were run on Linux.

## Convert URLs

Paste one direct PDF URL per line, or import a `.txt` URL list. Click **Download & convert**. Up to 20,000 URLs can be queued; they run one at a time. Each PDF has a 300 MB limit. The browser must stay open; the extension tab can close.

Each run creates `Documents\PDF_URL_Conversions\Batch_<date>_<id>` with:

- **originals/** — downloaded PDFs, unchanged.
- **converted/** — PDFs that passed the measured format checks, with matching numbered filenames and verification reports.
- **review/** — incomplete or noncompliant results, with explicit reasons. These are not counted as successful conversions.
- **conversion_status.xlsx** — one row per requested URL, requested/final URL, download status, conversion status, clickable original and converted files, page counts, measured font compliance, review issues and clickable HTML verification reports.
- **batch.json** — durable progress used to resume processing.

Use **Open folder** or **Open Excel**. Excel refreshes every 10 files and at completion/pause. Close Excel before refreshing; if Excel locks the report, close it and click **Refresh Excel**. Keep the Excel report with its subfolders so relative links continue to work. URL strings are stored as literal text, not formulas.

Use **Pause after current PDF**, then **Resume**. After browser closure, reopen the extension, select the saved batch and click **Resume**. Successful conversions are skipped. **Retry failures** retries failed, partial and unfinished entries. Restarting an interrupted conversion keeps its original download. Each URL gets its own row, including duplicate URLs. The selector shows the 200 most recent batches; older folders remain on disk.

Public HTTP(S) PDF URLs are supported. Browser cookies are not copied. Login pages, invalid PDFs, unavailable URLs, and unsupported layouts receive explicit failure entries. The application never uploads the PDFs to a conversion service.

## Alignment fix

Previously, all numeric table cells were right-aligned and all merged cells were top-aligned. This moved values such as 4, 2 and 1 away from the centred “Unlimited” layout. v1.8 detects short source-centred cell contents and retains horizontal centring, plus vertical centring in merged cells when the original provides evidence for it. Financial values without that evidence retain their numeric alignment.

The lounge-table screenshots guided this change. The actual lounge PDF was not available for exact-file regression testing; provide its PDF or direct URL for a verified conversion of that particular file.

## Output format and limitations

Existing conversion profiles, reference header/footer and margins are retained. Body/footer font size is **Mulish 11 pt**, matching Word's size 11 (not CSS 11 px). General output is A4 portrait. The legacy Form 20-F profile retains landscape for some financial tables; the final gate now flags those results for review. Reflow can change wrapping and pagination. Complex supported graphics may keep their original text/font, as documented in their validation report. The output status is **CONVERTED_REVIEW_LAYOUT** or **PARTIAL_REVIEW_REQUIRED** (original-font pages listed separately): automated checks do not guarantee all arbitrary PDFs reproduce perfectly. Originals remain available. See UPDATE_v2.0.md for preservation and interactive-content limitations.

## Troubleshooting

- **Host not found / disconnected:** rerun the installer from the permanent folder, reload the extension, and reconnect. Check the install window for Python/pip errors. Enterprise browser policy may block unpacked extensions or native messaging.
- **Another batch is running:** pause the current batch and wait for its current PDF to finish before starting another. The native helper prevents concurrent writes to one batch.
- **Report locked:** close Excel, then Refresh Excel.
- **URL returned HTML:** provide a direct PDF download URL accessible without signing in.
- **Conversion failed:** inspect the Excel Details column. The original PDF remains in originals if its download succeeded.

To remove: remove the extension in the browser, delete the per-user registry entries `Software\Google\Chrome\NativeMessagingHosts\com.local.a4_pdf_converter` and `Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.local.a4_pdf_converter`, then delete this package folder. Your batch output folders remain separate.

Native messaging reference: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
