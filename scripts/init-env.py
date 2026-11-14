import os
import secrets
from pathlib import Path

path = Path(".env")
values = {
    "DB_PASSWORD": secrets.token_hex(24),
    "TEACHER_TOKEN": secrets.token_hex(24),
    "OTHER_TEACHER_TOKEN": secrets.token_hex(24),
    "STUDENT_TOKEN": secrets.token_hex(24),
    "GRAFANA_PASSWORD": secrets.token_hex(24),
    "IMAGE_TAG": "local",
}
with os.fdopen(
    os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w"
) as stream:
    stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
print("Created .env with distinct random credentials. Keep it private.")
