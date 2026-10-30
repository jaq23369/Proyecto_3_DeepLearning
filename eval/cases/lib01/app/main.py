from datetime import date, timedelta

from fastapi import FastAPI, HTTPException

from app.config import FINE_PER_DAY, LOAN_DAYS, MAX_LOANS
from app.models import Loan, LoanCreate

app = FastAPI(title="Library Loans API")

TITLES = {1: "Don Quijote", 2: "Rayuela", 3: "Pedro Paramo"}
COPIES = {1: 5, 2: 1, 3: 5}
LOANS: dict[int, Loan] = {}


@app.get("/books")
def list_books():
    return [{"id": i, "title": TITLES[i], "free_copies": COPIES[i]} for i in TITLES]


@app.post("/loans", status_code=201)
def create_loan(data: LoanCreate) -> Loan:
    if data.book_id not in COPIES:
        raise HTTPException(status_code=404, detail="Unknown book")
    active = [x for x in LOANS.values() if x.member == data.member and not x.returned]
    if len(active) >= MAX_LOANS:
        raise HTTPException(status_code=409, detail="Loan limit reached")
    if COPIES[data.book_id] == 0:
        raise HTTPException(status_code=409, detail="No copies left")
    COPIES[data.book_id] -= 1
    loan = Loan(id=len(LOANS) + 1, due=date.today() + timedelta(days=LOAN_DAYS), **data.model_dump())
    LOANS[loan.id] = loan
    return loan


@app.post("/loans/{loan_id}/return")
def return_loan(loan_id: int, today: date | None = None) -> Loan:
    loan = LOANS.get(loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    late_days = max(0, ((today or date.today()) - loan.due).days)
    loan.fine = late_days * FINE_PER_DAY
    loan.returned = True
    COPIES[loan.book_id] += 1
    return loan


@app.get("/members/{member}/loans")
def member_loans(member: str) -> list[Loan]:
    return [x for x in LOANS.values() if x.member == member]
