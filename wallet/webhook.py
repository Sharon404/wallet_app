# wallet/webhook.py
import hmac
import hashlib
import json
import logging
from decimal import Decimal

from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import AllowAny
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from django.conf import settings
from .models import WalletTransaction, Wallet
from .models import Transaction


logger = logging.getLogger(__name__)

FLW_SECRET = settings.FLW_SECRET_KEY  # This is your secret key

@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([JSONParser])
def flutterwave_webhook(request):
    """
    Handle Flutterwave webhook for deposits / transfers.
    Sandbox-friendly but checks signature.
    """
    raw_body = request.body
    signature = request.META.get("HTTP_VERIF_HASH")  # Flutterwave sends this

    # Verify signature (skip if not in sandbox)
    if signature:
        computed = hmac.new(FLW_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, signature):
            logger.warning("Invalid Flutterwave webhook signature!")
            return Response({"error": "Invalid signature"}, status=400)

    try:
        data = request.data or json.loads(raw_body or '{}')
        tx_data = data.get("data", {})

        tx_ref = (
            tx_data.get("tx_ref") 
            or tx_data.get("txRef")
            or data.get("tx_ref")
            or data.get("txRef")
        )
        status = (tx_data.get("status") or data.get("status") or "").lower()
        amount = tx_data.get("amount") or data.get("amount")
        currency = tx_data.get("currency") or tx_data.get("currency_code")
        customer_email = tx_data.get("customer", {}).get("email") or data.get("customer", {}).get("email")

        # Also support transfer events
        event = data.get("event") or tx_data.get("event") or data.get("event_type")

        # If this webhook is about a transfer (withdrawal) handle separately
        if event and str(event).lower().startswith("transfer"):
            reference = tx_data.get("reference") or data.get("reference")
            if not reference:
                logger.warning("Transfer webhook without reference: %s", data)
                return Response({"status": "ignored"})

            tx = WalletTransaction.objects.filter(
                reference=reference,
                status="pending"
            ).first()

            if not tx:
                logger.warning("No pending WalletTransaction found for reference: %s", reference)
                return Response({"status": "ignored"})

            wallet = Wallet.objects.get(user=tx.user)

            # Normalize event/status to decide outcome
            ev = str(event).lower()
            if ev in ("transfer.completed", "transfer.successful") or (status and status in ("successful", "success", "completed")):
                tx.status = "success"
                tx.save()

                # ensure we don't double-deduct: the amount was already deducted at initiation
                Transaction.objects.create(
                    wallet=wallet,
                    transaction_type="WITHDRAWAL",
                    amount=Decimal(tx.amount),
                    description=f"Flutterwave withdrawal: {reference}",
                    counterparty=getattr(tx, 'phone', None) or None,
                    currency_from=wallet.currency,
                    currency_to=wallet.currency,
                    exchange_rate=Decimal("1.00"),
                    status="success",
                )
            elif ev in ("transfer.failed", "transfer.reversed") or (status and status in ("failed", "error", "reversed")):
                tx.status = "failed"
                tx.save()
                # refund the user's wallet
                wallet.balance += Decimal(tx.amount)
                wallet.save()

            logger.info("Flutterwave withdrawal webhook processed: reference=%s event=%s", reference, event)
            return Response({"status": "received"})

        # Non-transfer path: treat as payment/deposit webhook
        if not tx_ref:
            logger.warning("Webhook received without tx_ref: %s", data)
            return Response({"status": "ignored"})

        # Locate pending WalletTransaction by provider reference
        tx = WalletTransaction.objects.filter(reference=tx_ref, status="pending").first()
        if not tx:
            logger.warning("No matching WalletTransaction found for tx_ref: %s", tx_ref)
            return Response({"status": "ignored"})

        if status in ("successful", "success", "completed"):
            tx.status = "success"
            tx.save()

            # Update user wallet balance
            wallet = Wallet.objects.get(user=tx.user)
            try:
                wallet.balance += Decimal(amount)
                wallet.save()
            except Exception:
                logger.exception("Failed to credit wallet for tx_ref=%s amount=%s", tx_ref, amount)

            # Record the transaction
            try:
                Transaction.objects.create(
                    wallet=wallet,
                    transaction_type="DEPOSIT",
                    amount=Decimal(amount),
                    description=f"Flutterwave deposit: {tx_ref}",
                    counterparty=customer_email,
                    currency_from=currency,
                    currency_to=wallet.currency,
                    exchange_rate=Decimal('1.00'),
                    status="success",
                )
            except Exception:
                logger.exception("Failed to create Transaction record for flw deposit tx_ref=%s", tx_ref)
        else:
            tx.status = "failed"
            tx.save()

        logger.info("Flutterwave webhook processed: tx_ref=%s, status=%s", tx_ref, status)

    except Exception as e:
        logger.exception("Error processing Flutterwave webhook: %s", e)
        return Response({"status": "error"}, status=500)

    return Response({"status": "received"})

# -------------------------------------------------
# Flutterwave WITHDRAWAL (Transfer) handling
# -------------------------------------------------
    if event.startswith("transfer."):
        reference = tx_data.get("reference")

        if not reference:
            logger.warning("Transfer webhook without reference: %s", data)
            return Response({"status": "ignored"})

        tx = WalletTransaction.objects.filter(
            reference=reference,
            status="pending",
            transaction_type="WITHDRAWAL"
        ).first()

        if not tx:
            logger.warning("No pending withdrawal found for reference: %s", reference)
            return Response({"status": "ignored"})

        wallet = Wallet.objects.get(user=tx.user)

    elif event == "transfer.completed":
        tx.status = "success"
        tx.save()

        wallet.balance -= Decimal(tx.amount)
        wallet.save()

        Transaction.objects.create(
            wallet=wallet,
            transaction_type="WITHDRAWAL",
            amount=Decimal(tx.amount),
            description=f"Flutterwave withdrawal: {reference}",
            counterparty=tx.destination,
            currency_from=wallet.currency,
            currency_to=wallet.currency,
            exchange_rate=Decimal("1.00"),
            status="success",
        )

    elif event in ["transfer.failed", "transfer.reversed"]:
        tx.status = "failed"
        tx.save()

    logger.info(
        "Flutterwave withdrawal webhook processed: reference=%s event=%s",
        reference,
        event
    )
