"""Create an admin user and sample events. Safe to run more than once.

Run: python -m app.scripts.seed
"""

import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.core.redis_client import redis_client
from app.core.security import hash_password
from app.domain.booking_rules import Role
from app.models import Event, User
from app.repositories.event_repo import EventRepository
from app.repositories.seat_repo import SeatRepository
from app.schemas.event import EventCreate
from app.services.cache_service import CacheService
from app.services.event_service import EventService

logger = logging.getLogger("seed")

ADMIN_EMAIL = "admin@ticketrush.dev"
DEV_ADMIN_PASSWORD = "admin12345"  # local development only; set SEED_ADMIN_PASSWORD elsewhere


# (title, description, venue, city, days from now, price in paise, rows, seats per row)
SAMPLE_EVENTS = [
    (
        "Arijit Singh Live",
        "An evening of live music.",
        "Jio World Garden",
        "Mumbai",
        30,
        249900,
        10,
        20,
    ),
    (
        "Stand-up Comedy Night",
        "Five comics, one mic.",
        "Phoenix Marketcity",
        "Pune",
        14,
        79900,
        5,
        10,
    ),
    ("Jazz by the Bay", "Smooth jazz under the stars.", "NCPA", "Mumbai", 5, 99900, 6, 14),
    (
        "Prateek Kuhad Tour",
        "Indie folk, full band.",
        "Phoenix Arena",
        "Bengaluru",
        21,
        179900,
        8,
        16,
    ),
    (
        "The Merchant of Venice",
        "A modern staging of the classic play.",
        "Prithvi Theatre",
        "Mumbai",
        10,
        59900,
        6,
        12,
    ),
    ("IPL Watch Party", "Big screen, bigger crowd.", "Social", "Pune", 3, 49900, 4, 12),
    (
        "Garba Night",
        "Dance till late with live dhol.",
        "Gymkhana Grounds",
        "Ahmedabad",
        18,
        39900,
        8,
        18,
    ),
    (
        "Sunburn Arena",
        "Electronic music festival night.",
        "NSCI Dome",
        "Mumbai",
        45,
        299900,
        10,
        20,
    ),
]


def sample_events() -> list[EventCreate]:
    now = datetime.now(UTC)
    return [
        EventCreate(
            title=title,
            description=description,
            venue=venue,
            city=city,
            starts_at=now + timedelta(days=days),
            price_paise=price,
            rows=rows,
            seats_per_row=per_row,
        )
        for title, description, venue, city, days, price, rows, per_row in SAMPLE_EVENTS
    ]


def main() -> None:
    configure_logging()
    with SessionLocal() as session:
        admin = session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if admin is None:
            password = os.environ.get("SEED_ADMIN_PASSWORD", DEV_ADMIN_PASSWORD)
            admin = User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(password),
                full_name="TicketRush Admin",
                role=Role.ADMIN,
            )
            session.add(admin)
            session.commit()
            logger.info("Created admin %s", ADMIN_EMAIL)
        else:
            logger.info("Admin %s already exists", ADMIN_EMAIL)

        service = EventService(
            session, EventRepository(session), SeatRepository(session), CacheService(redis_client)
        )
        for data in sample_events():
            if session.scalar(select(Event.id).where(Event.title == data.title)):
                logger.info("Event %r already exists", data.title)
                continue
            event = service.create_event(data, admin)
            logger.info("Created event %r with %s seats", event.title, event.total_seats)


if __name__ == "__main__":
    main()
