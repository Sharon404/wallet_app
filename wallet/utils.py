from django.core.mail import send_mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings
import random
import requests
from decimal import Decimal, ROUND_HALF_UP
from django.core.cache import cache
from .models import OTP
from django.utils import timezone
import os
from dotenv import load_dotenv


# --- Activation Email ---
def send_activation_email(user, request):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    activation_link = f"http://{request.get_host()}/api/activate/{uid}/{token}/"

    subject = "Activate your Wallet Account"
    message = f"""
    Hi {user.username},

    Please click the link below to activate your wallet account:
    {activation_link}

    If you didn't request this, please ignore this email.
    """
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])

# --- OTP ---
def send_otp(user):
    otp_code = str(random.randint(100000, 999999))

    # delete old OTPs
    OTP.objects.filter(user=user, is_verified=False).delete()

    # create new OTP record
    otp = OTP.objects.create(
        user=user,
        code=otp_code,
        created_at=timezone.now(),
        is_verified=False
    )

    print(f"Your OTP code is: {otp_code}")
    print("----------------------------------------------------")

    # optional: send via email
    send_mail(
        "Your Verification Code",
        f"Your OTP code is: {otp_code}",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True,
    )

    return otp

# --- Currency Conversion ---
load_dotenv()

EXCHANGE_API = "https://api.exchangerate.host/convert"
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY", "")
def get_currency_choices():
    return [
        ("KES", "KES"),
        ("USD", "USD"),
        ("EUR", "EUR"),
        ("GBP", "GBP"),
    ]


def convert_currency(amount: Decimal, from_currency: str, to_currency: str):
    """
    Returns (converted_amount: Decimal, rate: Decimal)
    Uses exchangerate.host convert endpoint and caches the 1-unit rate for 5 minutes.
    Raises Exception on failure.
    """
    if not from_currency:
        from_currency = "KES"
    if not to_currency:
        to_currency = from_currency

    # same-currency short circuit
    if from_currency == to_currency:
        return (
            amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            Decimal("1.0"),
        )

    cache_key = f"rate_{from_currency}_{to_currency}"
    rate = cache.get(cache_key)

    if rate is None:
        params = {"from": from_currency.upper(), "to": to_currency.upper(), "amount": 1}
        # Include API key under common parameter names if provided by env/settings.
        if EXCHANGE_API_KEY:
            # some providers expect access_key, others apikey/key
            params.update({
                "access_key": EXCHANGE_API_KEY,
                "apikey": EXCHANGE_API_KEY,
                "key": EXCHANGE_API_KEY,
            })
        try:
            print(f"[CONVERT_CURRENCY] Requesting rate: {from_currency} -> {to_currency}, API key present: {bool(EXCHANGE_API_KEY)}")
            resp = requests.get(EXCHANGE_API, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            print(f"[CONVERT_CURRENCY] API response: {data}")
        except Exception as e:
            print(f"[CONVERT_CURRENCY] Error: {e}")
            raise Exception(f"Exchange rate fetch failed: {e}")

        # If API returned an explicit error (e.g., missing access key), surface it
        if isinstance(data, dict) and data.get("success") is False:
            raise Exception(f"Exchange API error: {data.get('error')}")

        # Defensive parsing for multiple possible provider formats
        raw_rate = None
        # exchangerate.host returns 'info':{'rate':...} and 'result'
        if isinstance(data, dict):
            raw_rate = data.get("info", {}).get("rate") or data.get("result")
            # some APIs return rates mapping for base->symbols
            rates = data.get("rates")
            if raw_rate is None and isinstance(rates, dict):
                # try to pick to_currency in rates
                raw_rate = rates.get(to_currency.upper())

        if raw_rate in (None, "", "NaN"):
            raise Exception(f"Unexpected response format from exchange API: {data}")

        try:
            rate = Decimal(str(raw_rate))
        except Exception:
            raise Exception(f"Invalid rate value returned: {raw_rate}")

        # Cache the rate for 5 minutes
        cache.set(cache_key, rate, 300)

    # Make sure amount is safely parsed as Decimal
    try:
        amount = Decimal(str(amount))
    except Exception:
        raise Exception(f"Invalid amount value: {amount}")

    # Compute converted amount
    converted = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return converted, rate

# Utility function for converting currency (used in views)
def convert_currency_from(amount, from_currency, to_currency):
    converted, _ = convert_currency(amount, from_currency, to_currency)
    return converted