import hashlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","message":"%(message)s"}')
log = logging.getLogger("school")

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
        for statement in SCHEMA:
            conn.execute(text(statement))
        for uid, role, variable in [(1, "teacher", "TEACHER_TOKEN"), (2, "teacher", "OTHER_TEACHER_TOKEN"), (3, "student", "STUDENT_TOKEN")]:
            token = os.environ[variable]
            if len(token) < 24:
                raise RuntimeError("Demo tokens must contain at least 24 characters")
            conn.execute(text("INSERT INTO users VALUES (:id,:role,:hash) ON CONFLICT(id) DO UPDATE SET token_hash=excluded.token_hash"), {"id": uid, "role": role, "hash": digest(token)})
        conn.execute(text("INSERT INTO classes VALUES (1,'Synthetic Class A',1) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO classes VALUES (2,'Synthetic Class B',2) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO students VALUES (1,'Demo Student A',1),(2,'Demo Student B',2) ON CONFLICT DO NOTHING"))
    yield


app = FastAPI(title="School attendance API", lifespan=lifespan)


def actor(authorization: str = Header(default="")):
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Bearer token required")
    with engine.connect() as conn:
        user = conn.execute(text("SELECT id, role FROM users WHERE token_hash=:hash"), {"hash": digest(token)}).mappings().first()
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
        return [dict(row) for row in conn.execute(text("SELECT * FROM classes")).mappings()]


@app.get("/classes/{class_id}/students")
def students(class_id: int, user=Depends(actor)):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(text("SELECT * FROM students WHERE class_id=:id"), {"id": class_id}).mappings()]


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
            teacher = conn.execute(text("SELECT teacher_id FROM classes WHERE id=:id"), {"id": class_id}).scalar()
            if user["role"] != "teacher" or teacher != user["id"]:
                raise HTTPException(403, "Assigned teacher required")
            member = conn.execute(text("SELECT id FROM students WHERE id=:student AND class_id=:class"), {"student": body.student_id, "class": class_id}).scalar()
            if member is None:
                raise HTTPException(422, "Student does not belong to class")
            conn.execute(text("INSERT INTO attendance VALUES (:student,:class,:day,:session,:present,:teacher)"), {"student": body.student_id, "class": class_id, "day": body.day, "session": body.session.strip().lower(), "present": body.present, "teacher": user["id"]})
            conn.execute(text("INSERT INTO audit(actor_id,action,student_id) VALUES (:actor,'attendance_created',:student)"), {"actor": user["id"], "student": body.student_id})
    except IntegrityError:
        raise HTTPException(409, "Attendance already exists")
    log.info("attendance_created actor=%s class=%s student=%s", user["id"], class_id, body.student_id)
    return {"status": "recorded"}
