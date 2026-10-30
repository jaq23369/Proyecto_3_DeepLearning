from datetime import date

from pydantic import BaseModel


class LoanCreate(BaseModel):
    member: str
    book_id: int


class Loan(LoanCreate):
    id: int
    due: date
    returned: bool = False
    fine: float = 0.0
