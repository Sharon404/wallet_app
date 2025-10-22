from django.core.mail import send_mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings
import random
from django.core.cache import cache

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
    otp = str(random.randint(100000, 999999))
    cache.set(f"otp_{user.id}", otp, timeout=300)  # expires in 5 min

    subject = "Your Verification Code"
    message = f"Your OTP code is: {otp}"
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
