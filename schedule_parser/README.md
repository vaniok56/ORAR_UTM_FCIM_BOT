# Schedule parser

Python 3.11+. Install root `requirements.txt` for parser and bot tests.
`parser.py` preserves source text, merges and parity boundaries.
`audit_outputs.py` compares generated XLSX with source and optional PDF text.
PDF checks require Poppler's `pdftotext`; they do not prove visual placement.

Runtime uploads support five/six-day schedules. Sunday uploads reject explicitly.
They accept dean-layout XLSX with optional matching PDF, not legacy runtime
workbooks. Review and publish steps are documented in [RUN.md](../RUN.md#uploading-schedules).
Upper source row is ISO-even; lower is ISO-odd. Internal `odd_text`/`even_text`
names remain historical resolver tokens.

CLI helpers stay available:

```sh
python -m schedule_parser.parser --help
python -m schedule_parser.audit_outputs --help
python -m unittest test_schedule_ingest test_upload_status
```

Publication saves workbook-hash-matched `orarN.classifications.json` files.
Classification runs during processing; display reads the saved results and keeps
uncertain or unavailable classifications as raw text.

Required tests generate invented-text XLSX inputs. Historical/current dean-file
checks are optional; enable with `ORAR_PRIVATE_TESTS=1` when sources are present.
Local wizard/geometry, their tests and full instructions are ignored checkout
files. They share tracked parser/auditor code and need rechecking after API edits.

Audit CSV is spreadsheet-oriented and apostrophe-escapes formula/control prefixes.
Excel save/reopen may remove protection. Existing CLI JSON is machine-oriented.
