import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings


class RazorpayGatewayError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        payload=None,
    ):
        self.code = code
        self.status_code = status_code
        self.payload = payload
        super().__init__(message)


@dataclass(frozen=True)
class RazorpayPaymentSession:
    key_id: str
    provider_order_id: str
    amount_subunits: int
    currency: str
    receipt: str
    allowed_payment_methods: tuple[str, ...]
    expires_at: object | None


def amount_to_subunits(value) -> int:
    amount = Decimal(value).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return int(
        (amount * Decimal("100")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


class RazorpayGateway:
    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID.strip()
        self.key_secret = (
            settings.RAZORPAY_KEY_SECRET.strip()
        )
        self.webhook_secret = (
            settings.RAZORPAY_WEBHOOK_SECRET.strip()
        )
        self.base_url = (
            settings.RAZORPAY_API_BASE_URL.rstrip("/")
        )
        self.timeout = (
            settings.RAZORPAY_REQUEST_TIMEOUT_SECONDS
        )

    def _require_api_credentials(self):
        if not self.key_id or not self.key_secret:
            raise RazorpayGatewayError(
                "razorpay_credentials_missing",
                "Razorpay API credentials are not configured.",
            )

    def _request(
        self,
        *,
        method: str,
        path: str,
        payload=None,
    ):
        self._require_api_credentials()

        url = f"{self.base_url}/{path.lstrip('/')}"
        body = None

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        authentication = base64.b64encode(
            f"{self.key_id}:{self.key_secret}".encode(
                "utf-8"
            )
        ).decode("ascii")

        request = Request(
            url=url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Basic {authentication}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Chokher-Alo/1.0",
            },
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                response_body = response.read()
        except HTTPError as exc:
            error_body = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            try:
                error_payload = json.loads(error_body)
            except json.JSONDecodeError:
                error_payload = {"raw": error_body}

            raise RazorpayGatewayError(
                "razorpay_http_error",
                "Razorpay rejected the payment request.",
                status_code=exc.code,
                payload=error_payload,
            ) from exc
        except URLError as exc:
            raise RazorpayGatewayError(
                "razorpay_connection_error",
                "The Razorpay service could not be reached.",
            ) from exc

        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise RazorpayGatewayError(
                "razorpay_invalid_response",
                "Razorpay returned an invalid response.",
            ) from exc

    def create_order(
        self,
        *,
        amount_including_gst,
        currency: str,
        receipt: str,
        notes: dict,
    ):
        return self._request(
            method="POST",
            path="orders",
            payload={
                "amount": amount_to_subunits(
                    amount_including_gst
                ),
                "currency": currency,
                "receipt": receipt,
                "notes": notes,
            },
        )

    def fetch_payment(self, provider_payment_id: str):
        payment_id = quote(
            provider_payment_id,
            safe="",
        )

        return self._request(
            method="GET",
            path=f"payments/{payment_id}",
        )

    def verify_checkout_signature(
        self,
        *,
        provider_order_id: str,
        provider_payment_id: str,
        signature: str,
    ) -> bool:
        self._require_api_credentials()

        signed_data = (
            f"{provider_order_id}|{provider_payment_id}"
        ).encode("utf-8")

        expected = hmac.new(
            self.key_secret.encode("utf-8"),
            signed_data,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(
            expected,
            signature.strip(),
        )

    def verify_webhook_signature(
        self,
        *,
        raw_body: bytes,
        signature: str,
    ) -> bool:
        if not self.webhook_secret:
            raise RazorpayGatewayError(
                "razorpay_webhook_secret_missing",
                "The Razorpay webhook secret is not configured.",
            )

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(
            expected,
            signature.strip(),
        )
