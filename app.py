from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})  # relax CORS; tighten by origin if you want

# In-memory task storage (ephemeral on server restarts)
tasks = []
_next_id = 1

@app.route("/", methods=["GET"])
def health():
    return jsonify({"message": "Task Tide API running", "status": "ok"}), 200

# helpers
def find_task(task_id):
    for t in tasks:
        if t["id"] == task_id:
            return t
    return None

@app.route("/api/tasks", methods=["GET"])
def api_get_tasks():
    # basic filters
    q = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "").strip().lower()
    status = request.args.get("status", "").strip()
    sort = request.args.get("sort", "").strip()

    def match(t):
        if q and q not in (t.get("title","") + " " + t.get("description","")).lower():
            return False
        if category and category != (t.get("category","") or "").lower():
            return False
        if status and status != t.get("status",""):
            return False
        return True

    filtered = [t for t in tasks if match(t)]
    if sort == "due":
        filtered.sort(key=lambda x: (x.get("due_date") or ""))
    elif sort == "priority":
        pri_map = {"High": 0, "Medium": 1, "Low": 2}
        filtered.sort(key=lambda x: pri_map.get(x.get("priority"), 3))

    return jsonify(filtered), 200

@app.route("/api/stats", methods=["GET"])
def api_stats():
    total = len(tasks)
    completed = sum(1 for t in tasks if t.get("status") == "Completed")
    from datetime import datetime
    def is_overdue(t):
        dd = t.get("due_date")
        if not dd:
            return False
        try:
            return datetime.fromisoformat(dd) < datetime.now() and t.get("status") != "Completed"
        except Exception:
            return False
    overdue = sum(1 for t in tasks if is_overdue(t))
    return jsonify({"total": total, "completed": completed, "overdue": overdue}), 200

@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    global _next_id
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    task = {
        "id": _next_id,
        "title": title,
        "description": data.get("description") or "",
        "due_date": data.get("due_date") or "",
        "status": data.get("status") or "Pending",
        "priority": data.get("priority") or "Medium",
        "category": data.get("category") or "",
        "subtasks": data.get("subtasks") or []
    }
    tasks.insert(0, task)
    _next_id += 1
    return jsonify(task), 201

@app.route("/api/tasks/<int:task_id>", methods=["PUT", "PATCH"])
def api_update_task(task_id):
    task = find_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    data = request.get_json(force=True) or {}
    for k in ["title","description","due_date","status","priority","category","subtasks"]:
        if k in data:
            task[k] = data[k]
    return jsonify(task), 200

@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def api_delete_task(task_id):
    global tasks
    before = len(tasks)
    tasks = [t for t in tasks if t["id"] != task_id]
    if len(tasks) == before:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"ok": True, "deleted": task_id}), 200

if __name__ == "__main__":
    # On Render, use the provided PORT env var; locally defaults to 5000
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
