from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.config import MAX_GUESTS, MAX_NIGHTS


class BookingCreate(BaseModel):
    room: str
    guests: int = Field(ge=1, le=MAX_GUESTS)
    check_in: date
    check_out: date

    @model_validator(mode="after")
    def check_dates(self):
        nights = (self.check_out - self.check_in).days
        if nights <= 0:
            raise ValueError("check_out must be after check_in")
        if nights > MAX_NIGHTS:
            raise ValueError(f"A booking can last at most {MAX_NIGHTS} nights")
        return self


class Booking(BookingCreate):
    id: int
    status: str
