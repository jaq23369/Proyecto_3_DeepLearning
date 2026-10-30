from pydantic import BaseModel, Field

from helpdesk.config import MAX_TITLE


class TicketIn(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    priority: str = "normal"


class PriorityChange(BaseModel):
    priority: str


class Ticket(TicketIn):
    id: int
    status: str
