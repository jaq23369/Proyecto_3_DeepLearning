from typing import Literal

from pydantic import BaseModel


class TaskIn(BaseModel):
    title: str
    priority: Literal["low", "normal", "high"] = "normal"
