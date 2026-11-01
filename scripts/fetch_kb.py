"""Fetch the knowledge-base source at its pinned commit into rag/knowledge_base/_source (data only; nothing there is executed)."""
import os
import subprocess

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(HERE, "rag", "knowledge_base", "_source")
REPO = "https://github.com/CrashingGuru/ITUAIReadiness"
COMMIT = "84010da9e9c443afcceeccb86d1700a662223395"

if not os.path.isdir(DEST):
    subprocess.check_call(["git", "clone", "--filter=blob:none", "--sparse", REPO, DEST])
    subprocess.check_call(["git", "-C", DEST, "sparse-checkout", "set", "simulation/server/knowledge/InputDocs"])
subprocess.check_call(["git", "-C", DEST, "checkout", COMMIT])
print("source ready at", DEST)

import urllib.request  # noqa: E402

SUPP = os.path.join(HERE, "rag", "knowledge_base", "_supplement")
os.makedirs(SUPP, exist_ok=True)
for url in ("https://www.itu.int/dms_pubrec/itu-r/rec/s/R-REC-S.1503-4-202309-I!!PDF-E.pdf", "https://docs.fcc.gov/public/attachments/FCC-26-26A1.pdf",
            "https://www.itu.int/dms_pubrec/itu-r/rec/s/R-REC-S.524-8-200401-S!!PDF-E.pdf", "https://www.itu.int/dms_pubrec/itu-r/rec/sf/R-REC-SF.358-5-199510-W!!PDF-E.pdf"):
    dest = os.path.join(SUPP, url.rsplit("/", 1)[1])
    if not os.path.exists(dest):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
            f.write(r.read())
print("supplement ready at", SUPP)
