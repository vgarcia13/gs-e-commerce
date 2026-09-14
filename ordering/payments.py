import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

DECLINE_CARD = "4000000000000002"
EXAMPLE_CARD = "4242424242424242"


@dataclass(frozen=True)
class PaymentResult:
    success: bool
    reference: str = ""
    message: str = ""


class PaymentGateway(Protocol):
    def charge(self, amount: Decimal, card_number: str, idempotency_key: str) -> PaymentResult: ...


class FakePaymentGateway:
    """Approves every card except the documented decline number; no card data leaves this method."""

    def charge(self, amount: Decimal, card_number: str, idempotency_key: str) -> PaymentResult:
        if re.sub(r"\D", "", card_number) == DECLINE_CARD:
            return PaymentResult(success=False, message="The card was declined.")
        return PaymentResult(success=True, reference=f"FAKE-{uuid.uuid4().hex[:12].upper()}")


def get_payment_gateway() -> PaymentGateway:
    return FakePaymentGateway()
