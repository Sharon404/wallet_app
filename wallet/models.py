from django.db import models
from django.conf import settings
from decimal import Decimal
from django.contrib.auth.models import AbstractUser
import uuid
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import random

#  Custom User model
class CustomUser(AbstractUser):
    mobile = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return self.username

#  OTP model
class OTP(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"OTP for {self.user.username} - {self.code}"

    def is_valid(self):
        return timezone.now() < self.expires_at


#  Wallet model linked to CustomUser
CURRENCY_CHOICES = [
    # East Africa / nearby
    ('KES', 'Kenyan Shilling'),
    ('UGX', 'Ugandan Shilling'),
    ('TZS', 'Tanzanian Shilling'),
    ('RWF', 'Rwandan Franc'),
    ('BIF', 'Burundi Franc'),
    ('ZAR', 'South African Rand'),

    # Popular international currencies used by many Kenyans abroad
    ('USD', 'US Dollar'),
    ('GBP', 'British Pound'),
    ('EUR', 'Euro'),
    ('AED', 'UAE Dirham'),
    ('SAR', 'Saudi Riyal'),
    ('EGP', 'Egyptian Pound'),
    ('NGN', 'Nigerian Naira'),
]

class Wallet(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    wallet_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='KES')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s Wallet ({self.currency})"


# ✅ Transaction model
class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('TRANSFER', 'Transfer'),
        ('CONVERSION', 'Conversion'),
    ]

    #  Transaction status
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]

    transaction_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency_from = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='KES')
    currency_to = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='KES')
    converted_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    counterparty = models.EmailField(null=True, blank=True)  # for receiver/sender email
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    timestamp = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.amount} {self.currency_from} → {self.currency_to} ({self.status})"


#  Automatically create wallet for each new user
@receiver(post_save, sender=CustomUser)
def create_user_wallet(sender, instance, created, **kwargs):
    if created:
        # Only create a wallet if one does not already exist (registration serializer creates it explicitly with chosen currency)
        if not Wallet.objects.filter(user=instance).exists():
            Wallet.objects.create(user=instance, currency='KES')

