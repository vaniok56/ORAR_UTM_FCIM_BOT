"""Run inside regular image, with only synthetic inputs and network disabled."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

assert shutil.which("pdftotext")
sys.path.insert(0, "/src")
sys.path.insert(0, "/checks/tests")
import schedule_ingest
import schedule_parser
from test_schedule_ingest import ScheduleIngestTests
assert schedule_parser.__file__.startswith("/schedule_parser/")
assert not list(Path("/configs").glob("*.ini"))
assert not Path("/schedules").exists()
for path in ("/schedule_parser/app.py", "/schedule_parser/pdf_geometry.py", "/schedule_parser/test_app.py",
             "/contributors.csv", "/DEAN_UPLOAD_PLAN.md", "/transform schedule"):
    assert not Path(path).exists(), path
for path in ("/src/schedule_ingest.py", "/src/course_classification.py", "/src/script.py"):
    compile(Path(path).read_bytes(), path, "exec")
assert not list(Path("/").glob("test_*.py"))

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source, pdf = root / "source.xlsx", root / "official.pdf"
    ScheduleIngestTests().dean_source(source)
    text = b"BT /F1 12 Tf 40 740 Td (ANUL UNIVERSITAR 2026/2027 ANUL II SEMESTRUL I) Tj 0 -20 Td (c. Algebra Example A. 101 c. Logic Sample B. 102) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"\nendstream"]
    data, offsets = bytearray(b"%PDF-1.4\n"), []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    pdf.write_bytes(data)
    for attachment in (None, pdf):
        prepared = schedule_ingest.prepare_upload(source, attachment, 3, root / ("pdf" if attachment else "xlsx"), None, None)
        assert prepared.xlsx.is_file() and prepared.sidecar.is_file()
        assert prepared.findings == ()

subprocess.run(["python", "--version"], check=True)
print("Regular-image smoke passed: imports, Poppler, XLSX/PDF preparation, private-file exclusion")
