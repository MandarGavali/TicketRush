"""initial schema: users, events, seats, bookings, booking_seats

Revision ID: 0001
Revises:
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        # One account per email.
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("venue", sa.String(200), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.Column("total_seats", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("price_paise > 0", name="ck_events_price_positive"),
    )
    # Serves "WHERE city = ? ORDER BY starts_at" for the event list.
    op.create_index("ix_events_city_starts_at", "events", ["city", "starts_at"])

    op.create_table(
        "seats",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_label", sa.String(2), nullable=False),
        sa.Column("seat_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        # A physical seat exists once per event.
        sa.UniqueConstraint("event_id", "row_label", "seat_number", name="uq_seats_position"),
    )
    # Serves "available seats of an event" (seat map, available_seats count).
    op.create_index("ix_seats_event_status", "seats", ["event_id", "status"])

    op.create_table(
        "bookings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_id", sa.BigInteger(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("total_paise", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payment_ref", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        # A retried request with the same key cannot create a second booking.
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_bookings_user_idempotency_key"),
    )
    # Serves "my bookings, newest first".
    op.create_index("ix_bookings_user_created", "bookings", ["user_id", "created_at"])
    # Serves the expiry sweeper: "PENDING and expires_at < now".
    op.create_index("ix_bookings_status_expires", "bookings", ["status", "expires_at"])

    op.create_table(
        "booking_seats",
        sa.Column(
            "booking_id",
            sa.BigInteger(),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "seat_id",
            sa.BigInteger(),
            sa.ForeignKey("seats.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("booking_seats")
    op.drop_index("ix_bookings_status_expires", table_name="bookings")
    op.drop_index("ix_bookings_user_created", table_name="bookings")
    op.drop_table("bookings")
    op.drop_index("ix_seats_event_status", table_name="seats")
    op.drop_table("seats")
    op.drop_index("ix_events_city_starts_at", table_name="events")
    op.drop_table("events")
    op.drop_table("users")
