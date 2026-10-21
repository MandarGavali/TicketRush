from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, EmailTakenError
from app.core.security import create_access_token, hash_password, verify_password
from app.domain.booking_rules import Role
from app.models import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.rate_limiter import RateLimiter

LOGIN_SCOPE = "login"


class AuthService:
    def __init__(self, session: Session, users: UserRepository, limiter: RateLimiter) -> None:
        self.session = session
        self.users = users
        self.limiter = limiter

    def register(self, data: RegisterRequest) -> User:
        email = data.email.lower()
        if self.users.get_by_email(email):
            raise EmailTakenError("Email is already registered")
        user = User(
            email=email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            role=Role.USER,
        )
        self.users.add(user)
        try:
            self.session.commit()
        except IntegrityError:
            # Two sign-ups with the same email at the same moment: the unique constraint decides.
            self.session.rollback()
            raise EmailTakenError("Email is already registered") from None
        return user

    def login(self, data: LoginRequest, client_ip: str) -> TokenResponse:
        limit = settings.login_rate_limit_per_min
        self.limiter.check(LOGIN_SCOPE, client_ip, limit)

        user = self.users.get_by_email(data.email)
        if user is None or not verify_password(data.password, user.password_hash):
            self.limiter.record(LOGIN_SCOPE, client_ip)  # only failed attempts count
            # Same message for unknown email and wrong password: do not reveal which emails exist.
            raise AuthenticationError("Invalid email or password")

        token = create_access_token(user.id, user.role)
        return TokenResponse(access_token=token, expires_in=settings.jwt_expire_minutes * 60)
