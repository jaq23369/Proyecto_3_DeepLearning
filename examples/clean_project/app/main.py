from fastapi import FastAPI, HTTPException

from app.schemas import TaskIn
from app.store import add_task, all_tasks, mark_done

app = FastAPI(title="Task Board API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/tasks")
def list_tasks():
    return all_tasks()


@app.post("/tasks", status_code=201)
def create_task(data: TaskIn):
    return add_task(data.title, data.priority)


@app.post("/tasks/{task_id}/done")
def finish_task(task_id: int):
    task = mark_done(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
