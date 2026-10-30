from fastapi import APIRouter, HTTPException

from helpdesk.config import PRIORITIES
from helpdesk.schemas import PriorityChange, Ticket, TicketIn

router = APIRouter(prefix="/tickets")

TICKETS: dict[int, Ticket] = {}


def find_ticket(ticket_id: int) -> Ticket:
    ticket = TICKETS.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("", status_code=201)
def create_ticket(data: TicketIn) -> Ticket:
    if data.priority not in PRIORITIES:
        raise HTTPException(status_code=422, detail="Unknown priority")
    ticket = Ticket(id=len(TICKETS) + 1, status="open", **data.model_dump())
    TICKETS[ticket.id] = ticket
    return ticket


@router.get("")
def list_tickets(status: str | None = None) -> list[Ticket]:
    return [t for t in TICKETS.values() if status is None or t.status == status]


@router.post("/{ticket_id}/resolve")
def close_ticket(ticket_id: int) -> Ticket:
    ticket = find_ticket(ticket_id)
    ticket.status = "closed"
    return ticket


@router.patch("/{ticket_id}/priority")
def change_priority(ticket_id: int, data: PriorityChange) -> Ticket:
    if data.priority not in PRIORITIES:
        raise HTTPException(status_code=422, detail="Unknown priority")
    ticket = find_ticket(ticket_id)
    ticket.priority = data.priority
    return ticket
