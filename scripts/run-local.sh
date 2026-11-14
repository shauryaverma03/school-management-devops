#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export DATABASE_URL="sqlite:///./school-demo.db"
export TEACHER_TOKEN="local-demo-teacher-one-token-2026"
export OTHER_TEACHER_TOKEN="local-demo-teacher-two-token-2026"
export STUDENT_TOKEN="local-demo-student-view-token-2026"
echo "Open http://127.0.0.1:8000"
echo "Teacher token: $TEACHER_TOKEN"
echo "Second teacher token: $OTHER_TEACHER_TOKEN"
echo "Student token: $STUDENT_TOKEN"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
