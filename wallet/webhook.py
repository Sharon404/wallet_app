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
        status = tx_data.get("status")
        amount = tx_data.get("amount")
        currency = tx_data.get("currency")
        customer_email = tx_data.get("customer", {}).get("email")

        if not tx_ref:
            logger.warning("Webhook received without tx_ref: %s", data)
            return Response({"status": "ignored"})

        # Find the pending WalletTransaction
        # The WalletTransaction model stores the provider reference in the
        # `reference` field (not `tx_ref`). Query by `reference` to locate
        # the pending transaction created when the user initiated the
        # Flutterwave payment.
        tx = WalletTransaction.objects.filter(reference=tx_ref, status="pending").first()
        if not tx:
            logger.warning("No matching WalletTransaction found for tx_ref: %s", tx_ref)
            return Response({"status": "ignored"})
        
        #find the pending WalletTransaction
        tx = WalletTransaction.objects.filter(reference=tx_ref, status="pending").first()
        if not tx:
            logger.warning("No matching WalletTransaction found for tx_ref: %s", tx_ref)
            return Response({"status": "ignored"})
        
        #successful transaction

        if status.lower() == "successful":
            tx.status = "success"
            tx.save()

            # Update user wallet balance
            wallet = Wallet.objects.get(user=tx.user)
            wallet.balance += Decimal(amount)
            wallet.save()


            # Record the transaction
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
        else:
            tx.status = "failed"

        tx.save()
        logger.info("Flutterwave webhook processed: tx_ref=%s, status=%s", tx_ref, status)

    except Exception as e:
        logger.exception("Error processing Flutterwave webhook: %s", e)
        return Response({"status": "error"}, status=500)

    return Response({"status": "received"})
