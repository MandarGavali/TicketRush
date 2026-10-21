"""Create an admin user and two sample events. Safe to run more than once.

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


def sample_events() -> list[EventCreate]:
    now = datetime.now(UTC)
    return [
        EventCreate(
            title="Arijit Singh Live",
            description="An evening of live music.",
            venue="Jio World Garden",
            city="Mumbai",
            starts_at=now + timedelta(days=30),
            price_paise=249900,
            rows=10,
            seats_per_row=20,
        ),
        EventCreate(
            title="Stand-up Comedy Night",
            description="Five comics, one mic.",
            venue="Phoenix Marketcity",
            city="Pune",
            starts_at=now + timedelta(days=14),
            price_paise=79900,
            rows=5,
            seats_per_row=10,
        ),
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
