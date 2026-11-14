import csv
import hashlib
import io
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"level": record.levelname, "message": record.getMessage()})


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
log = logging.getLogger("school")
log.handlers = [handler]
log.setLevel(logging.INFO)
log.propagate = False
STARTED = time.monotonic()
REQUESTS = Counter(
    "school_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
LATENCY = Histogram("school_http_request_seconds", "Request duration", ["route"])

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, role TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL)",
    "CREATE TABLE IF NOT EXISTS classes (id INTEGER PRIMARY KEY, name TEXT NOT NULL, teacher_id INTEGER REFERENCES users(id))",
    "CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT NOT NULL, class_id INTEGER REFERENCES classes(id))",
    "CREATE TABLE IF NOT EXISTS attendance (student_id INTEGER REFERENCES students(id), class_id INTEGER REFERENCES classes(id), day DATE NOT NULL, session TEXT NOT NULL, present BOOLEAN NOT NULL, teacher_id INTEGER REFERENCES users(id), UNIQUE(student_id, class_id, day, session))",
    "CREATE TABLE IF NOT EXISTS audit (actor_id INTEGER NOT NULL, action TEXT NOT NULL, student_id INTEGER NOT NULL, recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
]


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


@asynccontextmanager
async def lifespan(app):
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # Serialize schema initialization and seeding across starting replicas.
            conn.execute(text("SELECT pg_advisory_xact_lock(8675309)"))
        for statement in SCHEMA:
            conn.execute(text(statement))
        for uid, role, variable in [
            (1, "teacher", "TEACHER_TOKEN"),
            (2, "teacher", "OTHER_TEACHER_TOKEN"),
            (3, "student", "STUDENT_TOKEN"),
        ]:
            token = os.environ[variable]
            if len(token) < 24:
                raise RuntimeError("Demo tokens must contain at least 24 characters")
            conn.execute(
                text(
                    "INSERT INTO users VALUES (:id,:role,:hash) ON CONFLICT(id) DO UPDATE SET token_hash=excluded.token_hash"
                ),
                {"id": uid, "role": role, "hash": digest(token)},
            )
        conn.execute(
            text(
                "INSERT INTO classes VALUES (1,'Synthetic Class A',1) ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO classes VALUES (2,'Synthetic Class B',2) ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO students VALUES (1,'Demo Student A',1),(2,'Demo Student B',2) ON CONFLICT DO NOTHING"
            )
        )
        for student_id, name, class_id in [
            (10, "Aarav Mehta", 1),
            (11, "Diya Shah", 1),
            (12, "Kabir Rao", 1),
            (13, "Mira Kapoor", 1),
            (14, "Rohan Sen", 2),
            (15, "Anaya Patel", 2),
            (16, "Ishaan Das", 2),
            (17, "Sara Ali", 2),
        ]:
            conn.execute(
                text(
                    "INSERT INTO students VALUES (:id,:name,:class) ON CONFLICT DO NOTHING"
                ),
                {"id": student_id, "name": name, "class": class_id},
            )
    yield


app = FastAPI(title="School attendance API", lifespan=lifespan)


def actor(authorization: str = Header(default="")):
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Bearer token required")
    with engine.connect() as conn:
        user = (
            conn.execute(
                text("SELECT id, role FROM users WHERE token_hash=:hash"),
                {"hash": digest(token)},
            )
            .mappings()
            .first()
        )
    if not user:
        raise HTTPException(401, "Invalid token")
    return dict(user)


@app.get("/health")
def health():
    return {"status": "alive"}


@app.get("/ready")
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.error("database_unavailable")
        raise HTTPException(503, "Database unavailable")
    return {"status": "ready"}


@app.get("/classes")
def classes(user=Depends(actor)):
    with engine.connect() as conn:
        return [
            dict(row) for row in conn.execute(text("SELECT * FROM classes")).mappings()
        ]


@app.get("/classes/{class_id}/students")
def students(class_id: int, user=Depends(actor)):
    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                text("SELECT * FROM students WHERE class_id=:id"), {"id": class_id}
            ).mappings()
        ]


class Attendance(BaseModel):
    student_id: int
    day: date
    session: str
    present: bool


@app.post("/classes/{class_id}/attendance", status_code=201)
def attendance(class_id: int, body: Attendance, user=Depends(actor)):
    if not body.session.strip() or len(body.session) > 64:
        raise HTTPException(422, "Session must contain 1–64 characters")
    try:
        with engine.begin() as conn:
            teacher = conn.execute(
                text("SELECT teacher_id FROM classes WHERE id=:id"), {"id": class_id}
            ).scalar()
            if user["role"] != "teacher" or teacher != user["id"]:
                raise HTTPException(403, "Assigned teacher required")
            member = conn.execute(
                text("SELECT id FROM students WHERE id=:student AND class_id=:class"),
                {"student": body.student_id, "class": class_id},
            ).scalar()
            if member is None:
                raise HTTPException(422, "Student does not belong to class")
            conn.execute(
                text(
                    "INSERT INTO attendance VALUES (:student,:class,:day,:session,:present,:teacher)"
                ),
                {
                    "student": body.student_id,
                    "class": class_id,
                    "day": body.day,
                    "session": body.session.strip().lower(),
                    "present": body.present,
                    "teacher": user["id"],
                },
            )
            conn.execute(
                text(
                    "INSERT INTO audit(actor_id,action,student_id) VALUES (:actor,'attendance_created',:student)"
                ),
                {"actor": user["id"], "student": body.student_id},
            )
    except IntegrityError:
        raise HTTPException(409, "Attendance already exists")
    log.info(
        "attendance_created actor=%s class=%s student=%s",
        user["id"],
        class_id,
        body.student_id,
    )
    return {"status": "recorded"}


app.mount(
    "/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static"
)


@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/me")
def me(user=Depends(actor)):
    return user


@app.get("/classes/{class_id}/attendance")
def records(class_id: int, day: date, session: str, user=Depends(actor)):
    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                text(
                    "SELECT student_id, present FROM attendance WHERE class_id=:class AND day=:day AND session=:session"
                ),
                {"class": class_id, "day": day, "session": session.strip().lower()},
            ).mappings()
        ]


@app.middleware("http")
async def observe(request, call_next):
    started = time.monotonic()
    request_id = uuid.uuid4().hex
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        elapsed = time.monotonic() - started
        REQUESTS.labels(request.method, path, str(status)).inc()
        LATENCY.labels(path).observe(elapsed)
        log.info(
            "request id=%s method=%s route=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            path,
            status,
            elapsed * 1000,
        )


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def teacher_only(user):
    if user["role"] != "teacher":
        raise HTTPException(403, "Teacher access required")


@app.get("/operations")
def operations(user=Depends(actor)):
    teacher_only(user)
    ready()
    with engine.connect() as conn:
        attendance_count = conn.execute(
            text("SELECT COUNT(*) FROM attendance")
        ).scalar()
        audit_count = conn.execute(text("SELECT COUNT(*) FROM audit")).scalar()
    return {
        "service": "schoolroom",
        "version": os.getenv("APP_VERSION", "local"),
        "environment": os.getenv("APP_ENV", "local"),
        "database": engine.dialect.name,
        "database_ready": True,
        "uptime_seconds": round(time.monotonic() - STARTED),
        "attendance_records": attendance_count,
        "audit_events": audit_count,
    }


@app.get("/audit")
def audit_events(user=Depends(actor)):
    teacher_only(user)
    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                text(
                    "SELECT a.actor_id, a.action, a.student_id, s.name, a.recorded_at "
                    "FROM audit a JOIN students s ON s.id=a.student_id "
                    "JOIN classes c ON c.id=s.class_id WHERE c.teacher_id=:teacher "
                    "ORDER BY a.recorded_at DESC LIMIT 50"
                ),
                {"teacher": user["id"]},
            ).mappings()
        ]


class AttendanceItem(BaseModel):
    student_id: int
    present: bool


class AttendanceBatch(BaseModel):
    day: date
    session: str = Field(min_length=1, max_length=64)
    entries: list[AttendanceItem] = Field(min_length=1, max_length=100)


@app.post("/classes/{class_id}/attendance/batch", status_code=201)
def batch_attendance(class_id: int, body: AttendanceBatch, user=Depends(actor)):
    session = body.session.strip().lower()
    ids = [entry.student_id for entry in body.entries]
    if not session or len(set(ids)) != len(ids):
        raise HTTPException(422, "Provide a session and unique students")
    try:
        with engine.begin() as conn:
            teacher = conn.execute(
                text("SELECT teacher_id FROM classes WHERE id=:id"), {"id": class_id}
            ).scalar()
            if user["role"] != "teacher" or teacher != user["id"]:
                raise HTTPException(403, "Assigned teacher required")
            members = set(
                conn.execute(
                    text("SELECT id FROM students WHERE class_id=:id"), {"id": class_id}
                ).scalars()
            )
            if not set(ids).issubset(members):
                raise HTTPException(422, "Student does not belong to class")
            for entry in body.entries:
                conn.execute(
                    text(
                        "INSERT INTO attendance VALUES (:student,:class,:day,:session,:present,:teacher)"
                    ),
                    {
                        "student": entry.student_id,
                        "class": class_id,
                        "day": body.day,
                        "session": session,
                        "present": entry.present,
                        "teacher": user["id"],
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO audit(actor_id,action,student_id) VALUES (:actor,'attendance_created',:student)"
                    ),
                    {"actor": user["id"], "student": entry.student_id},
                )
    except IntegrityError:
        raise HTTPException(
            409, "A student already has attendance for this session; no changes saved"
        )
    return {"status": "recorded", "count": len(body.entries)}


@app.get("/classes/{class_id}/attendance.csv")
def export_attendance(class_id: int, day: date, session: str, user=Depends(actor)):
    teacher_only(user)
    with engine.connect() as conn:
        teacher = conn.execute(
            text("SELECT teacher_id FROM classes WHERE id=:id"), {"id": class_id}
        ).scalar()
        if teacher != user["id"]:
            raise HTTPException(403, "Assigned teacher required")
        rows = conn.execute(
            text(
                "SELECT s.id, s.name, a.present FROM students s LEFT JOIN attendance a "
                "ON a.student_id=s.id AND a.class_id=s.class_id AND a.day=:day AND a.session=:session "
                "WHERE s.class_id=:class ORDER BY s.id"
            ),
            {"day": day, "session": session.strip().lower(), "class": class_id},
        ).mappings()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["student_id", "name", "date", "session", "status"])
        for row in rows:
            name = row["name"]
            if name.startswith(("=", "+", "-", "@")):
                name = "'" + name
            status = (
                "Pending"
                if row["present"] is None
                else ("Present" if row["present"] else "Absent")
            )
            safe_session = session.strip().lower()
            if safe_session.startswith(("=", "+", "-", "@")):
                safe_session = "'" + safe_session
            writer.writerow([row["id"], name, day, safe_session, status])
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="class-{class_id}-{day}.csv"'
        },
    )
