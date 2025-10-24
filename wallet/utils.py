from django.core.mail import send_mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings
import random
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