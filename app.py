from flask import Flask, jsonify, request, render_template

app = Flask(__name__, static_folder='.', template_folder='templates')

# In-memory task storage
tasks = []

# Serve frontend
@app.route('/')
def home():
    return render_template('index.html')

# API endpoint: get all tasks
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    return jsonify(tasks)

# API endpoint: create a task
@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.get_json()
    if not data or 'title' not in data:
        return jsonify({'error': 'Invalid task data'}), 400

    task = {
        'id': len(tasks) + 1,
        'title': data['title'],
        'completed': False
    }
    tasks.append(task)
    return jsonify(task), 201

# API endpoint: toggle task completion
@app.route('/api/tasks/<int:task_id>/toggle', methods=['PATCH'])
def toggle_task(task_id):
    for task in tasks:
        if task['id'] == task_id:
            task['completed'] = not task['completed']
            return jsonify(task)
    return jsonify({'error': 'Task not found'}), 404

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
