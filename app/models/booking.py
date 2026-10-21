from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.booking_rules import BookingStatus
from app.models.event import Event
from app.models.seat import Seat

# Join table (many-to-many): a booking has many seats; a seat can be in many bookings over time.
booking_seats = Table(
    "booking_seats",
    Base.metadata,
    Column("booking_id", ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True),
    Column("seat_id", ForeignKey("seats.id", ondelete="CASCADE"), primary_key=True),
)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        # Same user + same key = same request: the database rejects a second booking.
        UniqueConstraint("user_id", "idempotency_key", name="uq_bookings_user_idempotency_key"),
        Index("ix_bookings_user_created", "user_id", "created_at"),
        Index("ix_bookings_status_expires", "status", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    status: Mapped[str] = mapped_column(String(10), default=BookingStatus.PENDING)
    total_paise: Mapped[int]
    idempotency_key: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payment_ref: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    event: Mapped[Event] = relationship()
    seats: Mapped[list[Seat]] = relationship(
        secondary=booking_seats, order_by=(Seat.row_label, Seat.seat_number)
    )
