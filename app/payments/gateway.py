import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaymentResult:
    success: bool
    payment_ref: str | None
    message: str


class PaymentGateway(Protocol):
    """What BookingService needs from any payment provider (Razorpay, Stripe, or the fake below)."""

    def charge(self, amount_paise: int, token: str, reference: str) -> PaymentResult: ...

    def refund(self, payment_ref: str, amount_paise: int) -> None: ...


class FakePaymentGateway:
    """Works without a network. Token "fail" is declined, anything else is approved."""

    def charge(self, amount_paise: int, token: str, reference: str) -> PaymentResult:
        if token == "fail":
            return PaymentResult(success=False, payment_ref=None, message="Card declined")
        payment_ref = f"pay_{uuid.uuid4().hex[:12]}"
        logger.info("Charged %s paise for %s (%s)", amount_paise, reference, payment_ref)
        return PaymentResult(success=True, payment_ref=payment_ref, message="Approved")

    def refund(self, payment_ref: str, amount_paise: int) -> None:
        logger.info("Refunded %s paise for %s", amount_paise, payment_ref)
