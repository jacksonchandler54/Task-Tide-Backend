import os
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

app = Flask(__name__)
CORS(app)

# ----- Database (Render Postgres) -----
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")
# Ensure SSL on external URLs
if "sslmode=" not in DATABASE_URL:
    DATABASE_URL += ("&" if "?" in DATABASE_URL else "?") + "sslmode=require"

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)

def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            category VARCHAR(100) DEFAULT 'General',
            due_date DATE,
            completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
        """))

init_db()  # run on import (works under gunicorn)

# ----- Helpers -----
def rowmap(r):
    return {
        "id": r["id"],
        "title": r["title"],
        "category": r["category"],
        "due_date": r["due_date"].isoformat() if r["due_date"] else None,
        "completed": bool(r["completed"]),
        "created_at": r["created_at"].isoformat(),
        "updated_at": r["updated_at"].isoformat(),
    }

# ----- Routes -----
@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "message": "Task Tide API running"}), 200

@app.get("/api/tasks")
def list_tasks():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, title, category, due_date, completed, created_at, updated_at
            FROM tasks ORDER BY id DESC
        """)).mappings().all()
        return jsonify([rowmap(r) for r in rows]), 200

@app.post("/api/tasks")
def create_task():
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    category = (data.get("category") or "General").strip()
    due_date = data.get("due_date")  # "YYYY-MM-DD" or None
    completed = bool(data.get("completed", False))
    now = datetime.utcnow()

    with engine.begin() as conn:
        if due_date:
            row = conn.execute(text("""
                INSERT INTO tasks (title, category, due_date, completed, created_at, updated_at)
                VALUES (:title, :category, :due_date::date, :completed, :now, :now)
                RETURNING id, title, category, due_date, completed, created_at, updated_at
            """), {"title": title, "category": category, "due_date": due_date,
                   "completed": completed, "now": now}).mappings().first()
        else:
            row = conn.execute(text("""
                INSERT INTO tasks (title, category, completed, created_at, updated_at)
                VALUES (:title, :category, :completed, :now, :now)
                RETURNING id, title, category, due_date, completed, created_at, updated_at
            """), {"title": title, "category": category,
                   "completed": completed, "now": now}).mappings().first()
    return jsonify(rowmap(row)), 201

@app.put("/api/tasks/<int:task_id>")
def update_task(task_id: int):
    patch = request.get_json(force=True) or {}
    fields, params = [], {"id": task_id, "now": datetime.utcnow()}

    if "title" in patch:
        fields.append("title = :title"); params["title"] = patch["title"]
    if "category" in patch:
        fields.append("category = :category"); params["category"] = patch["category"]
    if "due_date" in patch:
        if patch["due_date"] in (None, ""):
            fields.append("due_date = NULL")
        else:
            fields.append("due_date = :due_date::date"); params["due_date"] = patch["due_date"]
    if "completed" in patch:
        fields.append("completed = :completed"); params["completed"] = bool(patch["completed"])
    if not fields:
        return jsonify({"error": "no valid fields to update"}), 400

    set_clause = ", ".join(fields) + ", updated_at = :now"
    with engine.begin() as conn:
        res = conn.execute(text(f"UPDATE tasks SET {set_clause} WHERE id = :id"), params)
        if res.rowcount == 0:
            return jsonify({"error": "not found"}), 404
        row = conn.execute(text("""
            SELECT id, title, category, due_date, completed, created_at, updated_at
            FROM tasks WHERE id = :id
        """), {"id": task_id}).mappings().first()
    return jsonify(rowmap(row)), 200

@app.delete("/api/tasks/<int:task_id>")
def delete_task(task_id: int):
    with engine.begin() as conn:
        res = conn.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task_id})
        if res.rowcount == 0:
            return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True}), 200

@app.get("/api/stats")
def stats():
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM tasks")).scalar_one()
        completed = conn.execute(text("SELECT COUNT(*) FROM tasks WHERE completed = TRUE")).scalar_one()
        overdue = conn.execute(text("""
            SELECT COUNT(*) FROM tasks
            WHERE completed = FALSE AND due_date IS NOT NULL AND due_date < CURRENT_DATE
        """)).scalar_one()
        by_cat = conn.execute(text("""
            SELECT category,
                   COUNT(*) AS count,
                   SUM(CASE WHEN completed THEN 1 ELSE 0 END) AS completed,
                   SUM(CASE WHEN NOT completed AND due_date IS NOT NULL AND due_date < CURRENT_DATE THEN 1 ELSE 0 END) AS overdue
            FROM tasks GROUP BY category ORDER BY count DESC
        """)).mappings().all()
    return jsonify({
        "total": int(total),
        "completed": int(completed),
        "overdue": int(overdue),
        "by_category": [
            {"name": r["category"], "count": int(r["count"]),
             "completed": int(r["completed"] or 0), "overdue": int(r["overdue"] or 0)}
            for r in by_cat
        ]
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
