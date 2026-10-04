# Pretranslated local websites

`batch_translate_websites.py` uses the local AI4Bharat/IndicTrans2 model to create one HTML copy per Indic language in this folder. Names follow the pattern `index-te.html`, `simulator-hi.html`, and so on.

The script starts with `index.html` and `simulator.html` in its `HTML_FILES` list. It also discovers every new root-level `*.html` page automatically while running. Existing language copies are skipped, so it only creates missing files.

Run a single scan with:

```powershell
python batch_translate_websites.py --once
```

Keep it running in the background to check for new HTML pages every 60 seconds:

```powershell
Start-Process -FilePath python -ArgumentList 'batch_translate_websites.py' -WorkingDirectory (Get-Location).Path -WindowStyle Hidden
```

Progress and errors are written to `translated_websites/batch_translate.log`. The first conversion can take a while because it creates up to 22 language copies for each source page. Later scans skip completed copies.

When a language copy exists, `web_app.py` opens that pretranslated page. If it has not been created yet, the source page opens in English until the batch converter creates it.

To add another language, add its short code and AI4Bharat language tag to `LANGUAGE_MAP` in `models/translate2.py`. The website language menu and server language allowlist also need that code.
