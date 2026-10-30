TASKS: dict[int, dict] = {}


def add_task(title: str, priority: str) -> dict:
    task = {"id": len(TASKS) + 1, "title": title, "priority": priority, "done": False}
    TASKS[task["id"]] = task
    return task


def all_tasks() -> list[dict]:
    return sorted(TASKS.values(), key=lambda t: t["id"], reverse=True)


def mark_done(task_id: int) -> dict | None:
    task = TASKS.get(task_id)
    if task is not None:
        task["done"] = True
    return task
