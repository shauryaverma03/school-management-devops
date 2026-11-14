import json
import subprocess
from pathlib import Path
from urllib.parse import quote

values = {}
for line in Path(".env").read_text().splitlines():
    if line and not line.startswith("#"):
        key, value = line.split("=", 1)
        values[key] = value
required = ["DB_PASSWORD", "TEACHER_TOKEN", "OTHER_TEACHER_TOKEN", "STUDENT_TOKEN"]
for key in required:
    if len(values.get(key, "")) < 24:
        raise SystemExit(f"{key} must contain at least 24 characters")
data = {key: values[key] for key in required}
data["DATABASE_URL"] = (
    "postgresql+psycopg://school:"
    + quote(values["DB_PASSWORD"], safe="")
    + "@db/school"
)
manifest = {
    "apiVersion": "v1",
    "kind": "Secret",
    "metadata": {"name": "school-secrets", "namespace": "school"},
    "type": "Opaque",
    "stringData": data,
}
# Supply secrets through stdin; never place credentials in command arguments or repository files.
subprocess.run(
    ["kubectl", "apply", "-f", "-"],
    input=json.dumps(manifest),
    text=True,
    check=True,
    stdout=subprocess.DEVNULL,
)
print("Updated school-secrets.")
