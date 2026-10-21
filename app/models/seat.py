from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domain.booking_rules import SeatStatus


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (
        UniqueConstraint("event_id", "row_label", "seat_number", name="uq_seats_position"),
        Index("ix_seats_event_status", "event_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    row_label: Mapped[str] = mapped_column(String(2))
    seat_number: Mapped[int]
    status: Mapped[str] = mapped_column(String(10), default=SeatStatus.AVAILABLE)
    # Copied from the event so a seat keeps its own price.
    price_paise: Mapped[int]

    @property
    def label(self) -> str:
        return f"{self.row_label}{self.seat_number}"
