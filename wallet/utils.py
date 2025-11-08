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
EXCHANGE_API = "https://api.exchangerate.host/convert"

def convert_currency(amount: Decimal, from_currency: str, to_currency: str):
    """
    Returns (converted_amount: Decimal, rate: Decimal)
    Caches the exchange rate for 5 minutes.
    """
    if from_currency == to_currency:
        return (amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                Decimal('1.0'))

    cache_key = f"rate_{from_currency}_{to_currency}"
    rate = cache.get(cache_key)
    if rate is None:
        params = {"from": from_currency, "to": to_currency, "amount": 1}
        resp = requests.get(EXCHANGE_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rate = Decimal(str(data['result']))  # result is amount for 1 unit; API returns float
        cache.set(cache_key, rate, 300)  # cache 5 minutes

    # Compute converted amount (use quantize)
    converted = (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return converted, rate