# FCIM Schedule Parser Lab

Terminal workflow for converting FCIM dean schedule workbooks into normalized
odd/even XLSX schedules and auditing them against source XLSX files and optional
official PDFs.

The app never scans an input directory. Every XLSX, PDF, and optional transform
reference must be selected explicitly.

## Requirements

- Python 3.10 or newer
- `openpyxl>=3.1.0`
- Poppler commands `pdftotext` and `pdftocairo` when PDF validation is used
- macOS `open` command for final convenience actions

Install dependencies:

```sh
python3 -m venv /tmp/orar-parser-venv
/tmp/orar-parser-venv/bin/pip install -r schedule_parser/requirements.txt
brew install poppler
```

Poppler is optional when every PDF is skipped.

## Run Wizard

From repository root:

```sh
python3 schedule_parser/app.py
```

Choose `1. New processing session`, then:

1. Choose `1. Add schedule files`.
2. Select all wanted XLSX and optional PDF files in Finder and drag them into
   Terminal together, or paste all paths on one line. Order does not matter.
3. Press Enter once to submit file list.
4. For each detected schedule, press Enter to accept PDF version or type custom
   version from `0` to `99`.
5. Review automatically paired schedules.
6. Choose `3. Process session` and confirm.

App pairs files by academic year, study year, and semester read from file
contents, not filenames. One prompt may contain one XLSX, one XLSX/PDF pair, or
all years at once. XLSX without PDF is accepted as XLSX-only. PDF without
matching XLSX and duplicate revisions are rejected rather than guessed.

A folder path is not accepted; select the actual file inside it. Enter `c` at a
file or version prompt to cancel.

### Version Rules

Version is read from the first one- or two-digit number immediately after the
semester in PDF filename:

```text
anul_iv_semestrul_vii-6.pdf   -> 6
anul_iii_semestrul_v-4-2.pdf -> 4
anul_i_semestrul_i-12.pdf    -> 12
```

Later filename suffixes are treated as local download-duplicate suffixes and
ignored. Missing PDF or unrecognized filename detects version `0`. Press Enter
to accept detected value, or type replacement number directly.

Wizard-generated `final_schedule.xlsx` stores:

- `A1`: numeric version
- `B1`: processing date as a real Excel date formatted `dd/mm/yyyy`

Version and date also appear in `session.json`, `summary.csv`, and `SUMMARY.md`.

### Advanced Options

After adding a schedule, choose `2. Advanced options` to attach an old transform
workbook. It supplies non-authoritative comparison values in
`candidate_review.xlsx`; it never controls final schedule values. Reference
dimensions, group headers, and timeslots must match source layout.

### Final Actions

After processing:

- `1`: open run folder
- `2`: open `SUMMARY.md`
- `3`: open every candidate-review workbook
- Enter: return to main menu
- `q`: quit

## Output

Each session creates a new immutable timestamped directory:

```text
~/Desktop/FCIM_schedule_runs/YYYY-MM-DD_HH-MM-SS-microseconds/
├── SUMMARY.md
├── summary.csv
├── session.json
├── run.log
└── 2026_2027_year_I_semester_I/
    ├── sources/
    │   ├── dean.xlsx
    │   ├── official.pdf              # omitted when skipped
    │   └── transform_reference.xlsx  # omitted when absent
    ├── final_schedule.xlsx
    ├── candidate_review.xlsx
    ├── source_review.xlsx
    ├── audit.csv
    ├── report.md
    └── official.png                  # omitted when PDF skipped
```

Selected inputs are copied before parsing. SHA-256 hashes are checked after
copying and recorded in `session.json`. Existing runs are never overwritten.

## Verdicts

- `SAFE + PDF`: generated schedule matches parser resolution of XLSX, and every
  unique XLSX source value was found in extracted PDF text.
- `SAFE, XLSX ONLY`: generated schedule matches XLSX; PDF validation was skipped.
- `FAILED`: processing failed or audit produced wrong, missing, extra, or unknown
  findings.

Important: PDF validation is textual, not coordinate-aware. `SAFE + PDF` does
not prove that each PDF value occupies the same visual group/day/time position.
XLSX-to-output validation is cell-, parity-, and merge-aware.

Warnings are not audit failures. `candidate_review.xlsx` contains unusual source
layouts that parser resolved automatically, plus any unresolved blocks.

## Year I Shared Columns

Current Year I source contains 42 logical groups in 40 physical columns. These
headers contain two groups each:

```text
R-263 / AI-264
AI-263 / R-264
```

Parser emits separate logical output columns while mapping each pair to shared
source column. Both groups therefore receive identical source-backed schedules.
Empty official group `SI-222` is retained.

## Validate Existing Output

Choose `2. Validate existing output` and provide:

1. Original source XLSX
2. Generated schedule XLSX
3. Optional matching official PDF

App writes `audit.csv` and `report.md` beside generated workbook. It asks before
replacing those files.

## Direct Tools

Parser CLI:

```sh
python3 schedule_parser/parser.py \
  /path/to/source.xlsx \
  --json /tmp/blocks.json \
  --pairs-json /tmp/pairs.json \
  --review-xlsx /tmp/source-review.xlsx \
  --schedule-xlsx /tmp/final-schedule.xlsx \
  --candidate-review-xlsx /tmp/candidates.xlsx
```

Add `--reference-xlsx /path/to/old-transform.xlsx` only when comparison hints
are wanted. Direct parser CLI does not assign app version/date metadata.

Auditor CLI:

```sh
python3 schedule_parser/audit_outputs.py \
  --source /path/to/source.xlsx \
  --output /path/to/final-schedule.xlsx \
  --official-pdf /path/to/official.pdf \
  --csv /tmp/audit.csv \
  --report /tmp/report.md
```

Omit `--official-pdf` for XLSX-only validation.

## Tests

```sh
python3 -m unittest discover -s schedule_parser -p 'test_*.py'
python3 -m py_compile \
  schedule_parser/app.py \
  schedule_parser/parser.py \
  schedule_parser/audit_outputs.py \
  schedule_parser/test_app.py \
  schedule_parser/test_parser.py
```

Some current-schedule integration tests use manually supplied files under the
user home directory and skip when those files are absent. Repository fixtures
cover historical parser behavior.

See `PROJECT_KNOWLEDGE.md` for architecture, invariants, current validation
results, known limits, and maintainer guidance. That file is kept locally and
is not tracked in git.
