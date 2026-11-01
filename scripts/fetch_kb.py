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
