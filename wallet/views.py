from decimal import Decimal,InvalidOperation
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from django.views.decorators.csrf import csrf_exempt
import logging
from django.contrib.auth import get_user_model, authenticate
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
from .models import Wallet, Transaction, OTP, CustomUser, CURRENCY_CHOICES, WalletTransaction
import uuid
from .serializers import (
    WalletSerializer,
    WithdrawSerializer,
    TransactionSerializer,
    RegisterSerializer,
    LoginSerializer,
    VerifyOTPSerializer
)
from .utils import send_activation_email, send_otp
import random
from django.shortcuts import redirect 
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import status
from .models import CustomUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from django.db import transaction
from .utils import convert_currency
from .models import MpesaSTKRequest
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import parser_classes
import json
import hashlib, hmac
import os
from wallet.flutterwave import create_beneficiary, initiate_transfer




logger = logging.getLogger(__name__)


# Constants
LARGE_TRANSFER_THRESHOLD = Decimal('50000.00')
User = get_user_model()


# ---------------- REGISTER ----------------
@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save(is_active=False)  # inactive until activation
        send_activation_email(user, request)
        return Response({
            'message': 'Registration successful! Please check your email to activate your account.'
        }, status=status.HTTP_201_CREATED)
    print("❌ Registration serializer errors:", serializer.errors)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ---------------- ACTIVATE ACCOUNT ----------------
@api_view(['GET'])
@permission_classes([AllowAny])
def activate_account(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except Exception:
        return Response({'error': 'Invalid activation link.'}, status=status.HTTP_400_BAD_REQUEST)

    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        # Redirect user to your frontend login page
        return redirect("http://localhost:5173/login")  # change port if needed
    else:
        return Response({'error': 'Activation link invalid or expired.'}, status=status.HTTP_400_BAD_REQUEST)

# ---------------- LOGIN (SEND OTP) ----------------
@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        username_or_email = serializer.validated_data['username_or_email']
        password = serializer.validated_data['password']

        user = authenticate(request, username=username_or_email, password=password)

        if user is None:
            try:
                user_obj = User.objects.get(email=username_or_email)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                return Response({'error': 'Invalid credentials.'}, status=status.HTTP_400_BAD_REQUEST)

        if not user:
            return Response({'error': 'Invalid username/email or password.'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_active:
            return Response({'error': 'Please activate your account first.'}, status=status.HTTP_403_FORBIDDEN)

        send_otp(user)
        return Response({
            'message': 'Login successful. OTP sent to your email.',
            'user_id': user.id
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------- VERIFY OTP ----------------
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    user_id = request.data.get('user_id')
    code = request.data.get('otp')

    if not user_id or not code:
        return Response({'error': 'Missing user_id or otp.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Debug: print all OTPs for that user
    print("🔍 All OTPs for this user:")
    for o in OTP.objects.filter(user=user):
        print(o.code, o.created_at, o.is_verified)

    # Optional: expire OTPs older than 5 mins
    expiry_time = timezone.now() - timedelta(minutes=5)
    otp = OTP.objects.filter(user=user, is_verified=False, created_at__gte=expiry_time).order_by('-created_at').first()

    if not otp:
        return Response({'error': 'OTP not found or expired.'}, status=status.HTTP_400_BAD_REQUEST)

    print("Expected OTP:", otp.code)
    print("Received OTP:", code)

    if str(otp.code).strip() == str(code).strip():
        otp.is_verified = True
        otp.save()

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        return Response({
            'message': 'OTP verified successfully!',
            'token': access_token,
            'refresh': str(refresh)
        }, status=status.HTTP_200_OK)
    else:
        return Response({'error': 'Invalid OTP.'}, status=status.HTTP_400_BAD_REQUEST)


# ---------------- USER PROFILE ----------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    user = request.user
    wallet, _ = Wallet.objects.get_or_create(user=user)
    
    # Get user's transactions (Transaction model has transaction_type, amount, description, counterparty)
    transactions = Transaction.objects.filter(wallet=wallet).order_by('-timestamp')
    transaction_data = [
        {
            'transaction_type': t.transaction_type,
            'amount': str(t.amount),
            'description': t.description,
            'timestamp': t.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'counterparty': t.counterparty or 'N/A',  # Email or 'external'
        }
        for t in transactions
    ]

    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'wallet_balance': str(wallet.balance),
        'wallet_currency': getattr(wallet, 'currency', 'KES'),
        'transactions': transaction_data,
    })


# ---------------- CONVERT PREVIEW ----------------

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def convert_preview(request):
    """
    Expects JSON:
      { "amount": "1000", "currency_from": "KES" (optional), "currency_to": "GBP" }

    Returns:
      { "converted_amount": "5.30", "rate": "0.00530", "currency_from":"KES","currency_to":"GBP" }
    """
    try:
        amount_raw = request.data.get("amount")
        if amount_raw is None:
            return Response({"error": "Missing 'amount'."}, status=status.HTTP_400_BAD_REQUEST)

        # parse decimal safely
        amount = Decimal(str(amount_raw))

        # prefer explicit currency_from; otherwise use the user's wallet currency
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        from_currency = request.data.get("currency_from") or getattr(wallet, "currency", "KES")
        to_currency = request.data.get("currency_to")
        if not to_currency:
            return Response({"error": "Missing 'currency_to'."}, status=status.HTTP_400_BAD_REQUEST)

        converted_amount, rate = convert_currency(amount, from_currency, to_currency)

        return Response({
            "converted_amount": str(converted_amount),
            "rate": str(rate),
            "currency_from": from_currency,
            "currency_to": to_currency
        }, status=status.HTTP_200_OK)

    except Exception as e:
        # Don't expose internal trace in production — return helpful message
        return Response({"error": f"Conversion failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)


# ---------------- SUPPORTED CURRENCIES ----------------
@api_view(['GET'])
@permission_classes([AllowAny])
def currencies_list(request):
    """Return supported currency codes and labels."""
    data = [{'code': code, 'name': name} for code, name in CURRENCY_CHOICES]
    return Response({'currencies': data})


# ---------------- WALLET VIEW ----------------
class WalletView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        serializer = WalletSerializer(wallet)
        return Response(serializer.data)


# ---------------- DEPOSIT ----------------
class DepositView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            amount = Decimal(request.data.get('amount', '0'))
            if amount <= 0:
                return Response({'error': 'Amount must be greater than zero'}, status=400)

            wallet, _ = Wallet.objects.get_or_create(user=request.user)
            wallet.balance += amount
            wallet.save()

            Transaction.objects.create(
                wallet=wallet,
                transaction_type='DEPOSIT',
                amount=amount,
                description='Deposit successful'
            )

            return Response({
                'message': 'Deposit successful',
                'new_balance': str(wallet.balance)
            })

        except Exception as e:
            return Response({'error': str(e)}, status=500)


# ---------------- UNIFIED TRANSACTION FLOW ----------------
class TransactionFlowView(APIView):
    """Unified transaction endpoint.

    Expected JSON fields:
      - amount: decimal
      - source: 'wallet' or 'external'  (default 'wallet')
      - destination: 'wallet' or 'external'  (required)
      - recipient: username or email when destination is 'wallet' (optional — defaults to request.user)
      - receiver_email: email when destination is 'external'
      - currency_to: target currency code (e.g., 'KES', 'USD')
      - otp: optional otp for large transfers

    This view supports these flows:
      1. wallet -> wallet  (internal TRANSFER)
      2. wallet -> external (WITHDRAWAL)
      3. external -> wallet (DEPOSIT)

    It intentionally rejects external->external.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            amount = Decimal(request.data.get('amount', '0'))
            source = request.data.get('source', 'wallet')
            # default destination to 'wallet' for backward compatibility with existing frontend
            destination = request.data.get('destination', 'wallet')
            recipient = request.data.get('recipient') or request.data.get('receiver')
            receiver_email = request.data.get('receiver_email')
            currency_to = request.data.get('currency_to')
            otp = request.data.get('otp')
            pin = request.data.get('pin')

            if amount <= 0:
                return Response({'error': 'Positive amount is required.'}, status=400)

            # PIN verification required for all transfers from wallet
            if source == 'wallet':
                if not pin:
                    return Response({'error': 'PIN is required for transfers.'}, status=400)
                # Verify PIN
                if not request.user.check_pin(pin):
                    return Response({'error': 'Invalid PIN.'}, status=401)

            # wallet -> wallet
            if source == 'wallet' and destination == 'wallet':
                if not recipient:
                    return Response({'error': 'recipient is required for wallet->wallet transfers.'}, status=400)

                sender_wallet, _ = Wallet.objects.get_or_create(user=request.user)
                if sender_wallet.balance < amount:
                    return Response({'error': 'Insufficient balance.'}, status=400)

                # find recipient user
                try:
                    if '@' in recipient:
                        recv_user = User.objects.get(email=recipient)
                    else:
                        recv_user = User.objects.get(username=recipient)
                except User.DoesNotExist:
                    return Response({'error': 'Recipient not found.'}, status=400)

                recv_wallet, _ = Wallet.objects.get_or_create(user=recv_user)

                # OTP for large amounts
                if amount >= LARGE_TRANSFER_THRESHOLD and not otp:
                    return Response({'error': 'OTP required for large transfers.'}, status=400)

                with transaction.atomic():
                    if sender_wallet.currency == recv_wallet.currency:
                        rate = Decimal('1.00')
                        converted_amount = amount
                    else:
                        converted_amount, rate = convert_currency(amount, sender_wallet.currency, recv_wallet.currency)

                    sender_wallet.balance -= amount
                    sender_wallet.save()

                    recv_wallet.balance += converted_amount
                    recv_wallet.save()

                    Transaction.objects.create(
                        wallet=sender_wallet,
                        transaction_type='TRANSFER',
                        amount=amount,
                        currency_from=sender_wallet.currency,
                        currency_to=recv_wallet.currency,
                        converted_amount=converted_amount,
                        exchange_rate=rate,
                        counterparty=recv_user.email,
                        status='SUCCESS',
                        description=f'Sent to {recv_user.email}'
                    )

                    Transaction.objects.create(
                        wallet=recv_wallet,
                        transaction_type='TRANSFER',
                        amount=converted_amount,
                        currency_from=sender_wallet.currency,
                        currency_to=recv_wallet.currency,
                        converted_amount=converted_amount,
                        exchange_rate=rate,
                        counterparty=request.user.email,
                        status='SUCCESS',
                        description=f'Received from {request.user.email}'
                    )

                return Response({'message': 'Transfer successful', 'sender_balance': str(sender_wallet.balance)}, status=200)

            # wallet -> external (withdraw/send out)
            if source == 'wallet' and destination == 'external':
                # require receiver_email
                if not receiver_email:
                    return Response({'error': 'receiver_email is required for wallet->external transfers.'}, status=400)

                wallet, _ = Wallet.objects.get_or_create(user=request.user)
                if wallet.balance < amount:
                    return Response({'error': 'Insufficient balance.'}, status=400)

                with transaction.atomic():
                    if wallet.currency == currency_to:
                        converted_amount = amount
                        rate = Decimal('1.00')
                    else:
                        converted_amount, rate = convert_currency(amount, wallet.currency, currency_to)

                    wallet.balance -= amount
                    wallet.save()

                    Transaction.objects.create(
                        wallet=wallet,
                        transaction_type='WITHDRAWAL',
                        amount=amount,
                        currency_from=wallet.currency,
                        currency_to=currency_to,
                        converted_amount=converted_amount,
                        exchange_rate=rate,
                        counterparty=receiver_email,
                        status='PENDING',
                        description=f'Withdrawal to {receiver_email}'
                    )

                    return Response({
                        'message': 'Withdrawal initiated',
                        'new_balance': str(wallet.balance),
                        'converted_amount': str(converted_amount),
                        'rate': str(rate)
                    }, status=200)

            # external -> wallet (deposit from external source)
            if source == 'external' and destination == 'wallet':
                # default recipient to request.user if not provided
                if not recipient:
                    recipient_user = request.user
                else:
                    try:
                        if '@' in recipient:
                            recipient_user = User.objects.get(email=recipient)
                        else:
                            recipient_user = User.objects.get(username=recipient)
                    except User.DoesNotExist:
                        return Response({'error': 'Recipient not found.'}, status=400)

                recv_wallet, _ = Wallet.objects.get_or_create(user=recipient_user)

                with transaction.atomic():
                    if recv_wallet.currency == currency_to or not currency_to:
                        converted_amount = amount
                        rate = Decimal('1.00')
                    else:
                        converted_amount, rate = convert_currency(amount, currency_to, recv_wallet.currency)

                    recv_wallet.balance += converted_amount
                    recv_wallet.save()

                    Transaction.objects.create(
                        wallet=recv_wallet,
                        transaction_type='DEPOSIT',
                        amount=converted_amount,
                        currency_from=currency_to or recv_wallet.currency,
                        currency_to=recv_wallet.currency,
                        converted_amount=converted_amount,
                        exchange_rate=rate,
                        counterparty='external',
                        status='SUCCESS',
                        description=f'Deposit from external source'
                    )

                return Response({'message': 'Deposit successful', 'new_balance': str(recv_wallet.balance)}, status=200)

            return Response({'error': 'Unsupported source/destination combination.'}, status=400)

        except Exception as e:
            return Response({'error': str(e)}, status=500)


# ---------------- M-PESA STK PUSH ----------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_stk(request):
    phone = request.data.get("phone")
    amount = request.data.get("amount")

    # Print auth header and user info for debugging
    try:
        print("[STK] HTTP_AUTHORIZATION:", request.META.get('HTTP_AUTHORIZATION'))
        print("[STK] request.user:", getattr(request, 'user', None), "authenticated:", getattr(request.user, 'is_authenticated', False))
    except Exception as e:
        print("[STK] Error printing auth info:", e)

    if not phone or not amount:
        return Response({"error": "Phone and amount required"}, status=400)

    from .mpesa import stk_push
    res = stk_push(phone, amount)

    # Debug/trace: log full STK response so we can see what's returned by Safaricom
    try:
        logger.info("STK push result: %s", res)
        print("[STK RESULT]:", res)
    except Exception:
        pass

    # If mpesa.py returned an explicit error dict, forward it to the frontend
    if isinstance(res, dict) and res.get("error"):
        return Response(res, status=500)

    # If STK push looks successful, create a pending WalletTransaction that the
    # callback can later match using CheckoutRequestID or MerchantRequestID.
    try:
        ref = res.get('CheckoutRequestID') or res.get('MerchantRequestID')
        response_code = res.get('ResponseCode')

        # When sandbox returns success (accepted for processing), persist a
        # MpesaSTKRequest (so callback can map back to the user) and create a
        # pending WalletTransaction as a fallback (if not already created).
        if response_code == '0' and ref:
            print("✔ STK push looks successful")
            try:
                # Create or get the STK request mapping
                amount_dec = None
                try:
                    amount_dec = Decimal(str(amount))
                except Exception:
                    pass

                MpesaSTKRequest.objects.get_or_create(
                    checkout_request_id=ref,
                    defaults={
                        'user': request.user,
                        'amount': amount_dec or Decimal('0.00'),
                        'phone': phone,
                    }
                )
                print("✔ Saved STK request record for callback mapping")

                # Ensure we have a pending WalletTransaction tied to the reference
                tx_ref = ref
                if not WalletTransaction.objects.filter(reference=tx_ref).exists():
                    WalletTransaction.objects.create(
                        user=request.user,
                        phone=phone,
                        amount=amount_dec or Decimal('0.00'),
                        type='deposit',
                        status='pending',
                        reference=tx_ref
                    )
                # Create a pending Transaction record so the deposit appears in history
                try:
                    wallet_obj, _ = Wallet.objects.get_or_create(user=request.user)
                    if not Transaction.objects.filter(wallet=wallet_obj, description__icontains=str(tx_ref)).exists():
                        Transaction.objects.create(
                            wallet=wallet_obj,
                            transaction_type='DEPOSIT',
                            amount=amount_dec or Decimal('0.00'),
                            currency_from='KES',
                            currency_to=getattr(wallet_obj, 'currency', 'KES'),
                            converted_amount=amount_dec or Decimal('0.00'),
                            status='PENDING',
                            description=f'M-Pesa deposit reference {tx_ref} initiated'
                        )
                except Exception:
                    logger.exception('Failed to create pending Transaction record for STK ref=%s', tx_ref)
            except Exception as e:
                logger.exception('Failed to save STK request or pending transaction: %s', e)
    except Exception:
        logger.exception('Failed to process STK push response for pending transaction creation')

    return Response(res)


# ---------------- M-PESA CALLBACK ----------------
@api_view(["POST"])
@csrf_exempt
@permission_classes([AllowAny])
def mpesa_callback(request):
    data = request.data

    # Log raw callback body for debugging
    try:
        logger.info("Raw STK callback payload: %s", data)
        print("[STK CALLBACK RAW]:", data)
    except Exception:
        pass

    try:
        result = data.get("Body", {}).get("stkCallback", {})
        result_code = result.get("ResultCode")

        # Try to find a stable reference id
        reference = result.get("CheckoutRequestID") or result.get("MerchantRequestID")
        user = None
        if reference:
            try:
                req = MpesaSTKRequest.objects.get(checkout_request_id=reference)
                user = req.user
                print("✔ Matched user using MpesaSTKRequest:", user)
            except MpesaSTKRequest.DoesNotExist:
                pass

        # Callback metadata may be missing in failure cases
        callback_meta = result.get("CallbackMetadata", {}).get("Item", [])

        # Helper to extract item by Name or fallback to indices
        def _get_item_value(items, name=None, idx=None):
            try:
                if name:
                    for it in items:
                        if isinstance(it, dict) and it.get("Name") == name:
                            return it.get("Value")
                if idx is not None and idx < len(items):
                    it = items[idx]
                    return it.get("Value") if isinstance(it, dict) else None
            except Exception:
                return None
            return None

        amount = (
    _get_item_value(callback_meta, name="Amount") or
    _get_item_value(callback_meta, name="TransAmount") or
    _get_item_value(callback_meta, name="amount") or
    _get_item_value(callback_meta, idx=0)
)
        phone = _get_item_value(callback_meta, name="PhoneNumber", idx=4)
        # try MpesaReceiptNumber too for better reference
        mpesa_receipt = _get_item_value(callback_meta, name="MpesaReceiptNumber", idx=1)
        if not reference:
            reference = mpesa_receipt

        # Cast amount safely
        try:
            amount_val = Decimal(str(amount)) if amount is not None else None
        except Exception:
            amount_val = None
            print("[CALLBACK] Extracted Amount =", amount_val)

       # ---------- PRIMARY MATCH: WalletTransaction (pending) ----------
        tx_by_ref = None
        if reference:
            try:
                tx_by_ref = WalletTransaction.objects.filter(
    reference=reference,
    status="pending"
).first()
                if tx_by_ref:
                    user = tx_by_ref.user
                    try:
                        amount_val = tx_by_ref.amount if tx_by_ref.amount is not None else amount_val
                    except Exception:
                        pass
                    logger.info("Found pending WalletTransaction by reference %s -> user=%s amount=%s", reference, user, amount_val)
            except Exception:
                tx_by_ref = None

        # ---------- SECOND MATCH: MpesaSTKRequest fallback ----------
        if not user and reference:
            try:
                locked_user = MpesaSTKRequest.objects.get(checkout_request_id=reference).user
                user = locked_user
                logger.info("Matched user using MpesaSTKRequest fallback")
            except MpesaSTKRequest.DoesNotExist:
                pass

        # ---------- THIRD MATCH: Phone number (only if allowed) ----------
        # IMPORTANT: DO NOT reset user = None here (this was breaking everything)
        if not user and phone:
            try:
                phone_str = str(phone).strip()
            except Exception:
                phone_str = None

            if phone_str:
                digits = ''.join(ch for ch in phone_str if ch.isdigit())
            else:
                digits = None

            lookup_candidates = set()
            if digits:
                lookup_candidates.add(digits)
                lookup_candidates.add(digits.lstrip('+'))

                if digits.startswith('0') and not digits.startswith('254'):
                    lookup_candidates.add('254' + digits.lstrip('0'))

                if digits.startswith('254'):
                    lookup_candidates.add('0' + digits[3:])

                last9 = digits[-9:]
                lookup_candidates.add(last9)

            logger.info("STK callback phone normalization: raw=%s digits=%s candidates=%s",
                        phone, digits, lookup_candidates)

            from .models import CustomUser
            for p in list(lookup_candidates):
                try:
                    if not p:
                        continue
                    found = CustomUser.objects.filter(mobile=p).first()
                    if found:
                        user = found
                        logger.info("Matched user by mobile exact: %s -> %s", p, user)
                        break
                except Exception:
                    pass

            if not user and digits:
                try:
                    last9 = digits[-9:]
                    found = CustomUser.objects.filter(mobile__endswith=last9).first()
                    if found:
                        user = found
                        logger.info("Matched user by mobile endswith last9: %s -> %s", last9, user)
                except Exception:
                    pass

        # ---------- FINAL PROTECTION ----------
        if not user:
            logger.error(f"Callback arrived but NO USER matched. REF={reference}")
            return Response({"Result": "Callback received (no user matched)"})

        # ---------- PROCESS SUCCESS ----------
        if result_code == 0 and amount_val is not None:
            try:
                # Ensure wallet + transaction are updated atomically so the UI can rely
                # on a consistent state when polling status endpoints.
                with transaction.atomic():
                    wallet, _ = Wallet.objects.get_or_create(user=user)
                    wallet.balance += Decimal(amount_val)
                    wallet.save()

                    if tx_by_ref:
                        tx_by_ref.status = 'success'
                        tx_by_ref.amount = amount_val if (tx_by_ref.amount is None) else tx_by_ref.amount
                        tx_by_ref.phone = phone or tx_by_ref.phone
                        tx_by_ref.save()
                        logger.info('Updated existing WalletTransaction %s -> success', tx_by_ref.reference)
                    else:
                        ref = reference or str(uuid.uuid4())
                        WalletTransaction.objects.create(
                            user=user,
                            phone=phone,
                            amount=amount_val,
                            type="deposit",
                            status="success",
                            reference=ref
                        )

                # Record Transaction history (avoid duplicate entries for the same MPESA ref)
                try:
                    wallet_obj, _ = Wallet.objects.get_or_create(user=user)
                    t = Transaction.objects.filter(
                        wallet=wallet_obj,
                        description__icontains=str(reference)
                    ).order_by('-id').first()
                    if t:
                        t.status = 'SUCCESS'
                        t.amount = Decimal(amount_val)
                        t.converted_amount = Decimal(amount_val)
                        t.save()
                    else:
                        Transaction.objects.create(
                            wallet=wallet_obj,
                            transaction_type='DEPOSIT',
                            amount=Decimal(amount_val),
                            currency_from='KES',
                            currency_to=getattr(wallet_obj, 'currency', 'KES'),
                            converted_amount=Decimal(amount_val),
                            status='SUCCESS',
                            description=f'M-Pesa deposit reference {reference} receipt {mpesa_receipt or "n/a"}'
                        )
                except Exception:
                    logger.exception('Failed to create Transaction record for successful MPesa deposit ref=%s', reference)

                logger.info(f"Credited {amount_val} to {user}. Wallet new balance: {wallet.balance}")
            except Exception as e:
                logger.exception("Error crediting wallet on STK callback: %s", e)

        else:
            # ---------- FAILURE HANDLING ----------
            try:
                ref = reference or (mpesa_receipt or f"none-{random.randint(100000,999999)}")
                if tx_by_ref:
                    tx_by_ref.status = 'failed'
                    tx_by_ref.amount = amount_val or tx_by_ref.amount or Decimal('0.00')
                    tx_by_ref.phone = phone or tx_by_ref.phone
                    tx_by_ref.save()
                    logger.info('Marked pending WalletTransaction %s as failed', tx_by_ref.reference)
                else:
                    WalletTransaction.objects.create(
                        user=user,
                        phone=phone,
                        amount=amount_val or Decimal('0.00'),
                        type="deposit",
                        status="failed",
                        reference=ref
                    )
            except Exception as e:
                logger.exception("Error recording failed STK callback: %s", e)

                # Also record failed deposit attempt in Transaction history
                try:
                    w, _ = Wallet.objects.get_or_create(user=user)
                    t = Transaction.objects.filter(wallet=w, description__icontains=str(reference)).order_by('-id').first()
                    if t:
                        t.status = 'FAILED'
                        t.amount = Decimal(amount_val or 0)
                        t.converted_amount = Decimal(amount_val or 0)
                        t.save()
                    else:
                        Transaction.objects.create(
                            wallet=w,
                            transaction_type='DEPOSIT',
                            amount=Decimal(amount_val or 0),
                            currency_from='KES',
                            currency_to=getattr(w, 'currency', 'KES'),
                            converted_amount=Decimal(amount_val or 0),
                            status='FAILED',
                            description=f'Failed M-Pesa deposit reference {reference} receipt {mpesa_receipt or "n/a"}'
                        )
                except Exception:
                    logger.exception('Failed to create Transaction record for failed MPesa deposit ref=%s', reference)

    except Exception as e:
        logger.exception("Callback Error: %s", e)

    return Response({"Result": "Callback received"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_stk_status(request):
    """Return the status of a WalletTransaction created for a previous STK push.

    Query parameters: reference (CheckoutRequestID / MerchantRequestID)

    This is used by the frontend to poll for the STK completion result so the
    UI can update immediately without needing the user to logout/login.
    """
    reference = request.query_params.get('reference') or request.GET.get('reference')
    if not reference:
        return Response({'error': 'reference query parameter is required'}, status=400)

    try:
        tx = WalletTransaction.objects.filter(reference=reference).order_by('-id').first()
        # If transaction missing, fall back to STK request mapping to ensure the
        # requested reference belongs to the current user.
        if not tx:
            req = MpesaSTKRequest.objects.filter(checkout_request_id=reference).first()
            if req and req.user != request.user:
                return Response({'error': 'forbidden'}, status=403)

            return Response({'status': 'unknown', 'reference': reference})

        if tx.user != request.user:
            return Response({'error': 'forbidden'}, status=403)

        wallet = Wallet.objects.filter(user=request.user).first()

        return Response({
            'status': tx.status,
            'amount': str(tx.amount) if tx.amount is not None else None,
            'phone': tx.phone,
            'reference': tx.reference,
            'wallet_balance': str(wallet.balance) if wallet else None,
        })

    except Exception as e:
        logger.exception('Error checking STK status for ref=%s: %s', reference, e)
        return Response({'error': 'server error'}, status=500)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def get_withdraw_status(request):
    """Return the status of a withdraw WalletTransaction by our internal reference.

    Query parameter: reference (the UUID returned from withdraw API)
    """
    reference = request.query_params.get('reference') or request.GET.get('reference')
    if not reference:
        return Response({'error': 'reference query parameter is required'}, status=400)

    # Perform safe manual JWT authentication if an Authorization header is present.
    # We disable automatic authentication for this view (see decorator) to avoid
    # DRF returning 401 when an invalid/expired token is provided. Instead we
    # try to authenticate manually and ignore failures so unauthenticated clients
    # can still query status.
    try:
        auth_hdr = request.META.get('HTTP_AUTHORIZATION')
        if auth_hdr:
            try:
                auth = JWTAuthentication()
                auth_result = auth.authenticate(request)
                if auth_result:
                    request.user, _ = auth_result
            except Exception:
                # Ignore authentication errors and continue as unauthenticated
                logger.info('Withdraw status: manual JWT auth failed or expired token; continuing unauthenticated')

    except Exception:
        logger.exception('Error during manual auth for withdraw status')

    try:
        tx = WalletTransaction.objects.filter(reference=reference).order_by('-id').first()
        if not tx:
            return Response({'status': 'unknown', 'reference': reference})

        # If request is authenticated, only the owner may read full details
        if getattr(request, 'user', None) and request.user.is_authenticated:
            if tx.user != request.user:
                return Response({'error': 'forbidden'}, status=403)

            wallet = Wallet.objects.filter(user=request.user).first()
            return Response({
                'status': tx.status,
                'amount': str(tx.amount) if tx.amount is not None else None,
                'phone': tx.phone,
                'reference': tx.reference,
                'wallet_balance': str(wallet.balance) if wallet else None,
            })

        # Unauthenticated requests get limited info (status, amount, phone, reference)
        return Response({
            'status': tx.status,
            'amount': str(tx.amount) if tx.amount is not None else None,
            'phone': tx.phone,
            'reference': tx.reference,
        })

    except Exception as e:
        logger.exception('Error checking withdraw status for ref=%s: %s', reference, e)
        return Response({'error': 'server error'}, status=500)

# ---------------- M-PESA WITHDRAWAL ----------------
@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def withdraw_from_wallet(request):
    phone = request.data.get("phone")
    amount_str = request.data.get("amount") 
    amount = int(float(amount_str)) 
    pin = request.data.get("pin")

    print("[WITHDRAW] HTTP_AUTHORIZATION:", request.META.get('HTTP_AUTHORIZATION'))
    print("[WITHDRAW] request.user:", request.user, "authenticated:", request.user.is_authenticated)

    # Debug: log auth header and user for troubleshooting 401s
    try:
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        logger.info(f"Withdraw called. Authorization header: {auth_header}")
        logger.info(f"Request user: {getattr(request, 'user', None)} | authenticated: {getattr(request, 'user', None).is_authenticated if getattr(request, 'user', None) else 'N/A'}")
    except Exception as e:
        logger.exception("Error logging auth info for withdraw")
    try:
        print("[WITHDRAW] HTTP_AUTHORIZATION:", request.META.get('HTTP_AUTHORIZATION'))
        print("[WITHDRAW] request.user:", getattr(request, 'user', None), "authenticated:", getattr(request.user, 'is_authenticated', False))
    except Exception as e:
        print("[WITHDRAW] Error printing auth info:", e)

    if not pin:
        return Response({"error": "PIN required for withdrawal"}, status=400)

    if not request.user.check_pin(pin):
        return Response({"error": "Invalid PIN"}, status=401)

    # Convert amount to Decimal safely
    try:
        amount = Decimal(amount_str)
    except:
        return Response({"error": "Invalid amount format"}, status=400)

    wallet = Wallet.objects.get(user=request.user)

    # Compare Decimal -> Decimal
    if wallet.balance < amount:
        return Response({"error": "Insufficient balance"}, status=400)

    from .mpesa import mpesa_withdraw
    res = mpesa_withdraw(phone, amount)
    reference = str(uuid.uuid4())

    if res.get("ResponseCode") == "0":
        wallet.balance -= amount
        wallet.save()
        WalletTransaction.objects.create(
            user=request.user,
            type="withdraw",
            amount=amount,
            status="pending",   # update via callback
            reference=reference,
        )
        # Create a pending Transaction record so it appears in the user's
        # transaction history immediately and can be updated by callback.
        try:
            Transaction.objects.create(
                wallet=wallet,
                transaction_type='WITHDRAWAL',
                amount=amount,
                currency_from=getattr(wallet, 'currency', 'KES'),
                currency_to=getattr(wallet, 'currency', 'KES'),
                converted_amount=amount,
                status='PENDING',
                description=f'M-Pesa withdraw reference {reference} phone {phone}'
            )
        except Exception:
            logger.exception('Failed to create initial Transaction record for withdraw ref=%s', reference)
    # Return the provider response plus our internal reference so the frontend
    # can poll for completion (B2C result) and show an immediate confirmation.
    payload = {
        'mpesa_response': res,
        'reference': reference,
        'wallet_balance': str(wallet.balance),
    }

    # If the provider returned success right away, include a friendly message
    if res.get('ResponseCode') == '0':
        payload['message'] = 'Withdrawal initiated — awaiting provider confirmation.'
    else:
        payload['message'] = 'Withdrawal request failed to start.'

    return Response(payload)


# ---------------- M-PESA B2C RESULT CALLBACK ----------------
@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def mpesa_b2c_result(request):
    result = request.data or json.loads(request.body.decode() or '{}')
    if "Result" not in result:
        return Response({"status": "ACK received"})
    logger.info("RAW B2C CALLBACK: %s", result)

    try:
        # If this is a preliminary acknowledgement, return 200
        if "Result" not in result:
            logger.info("ACK callback received, returning 200.")
            return Response({"Result": "Acknowledged"})

        result_obj = result.get("Result", {})
        result_code = result_obj.get("ResultCode", None)
        params_list = (
            result_obj.get("ResultParameters", {})
            .get("ResultParameter", [])
        )

        # Clean parsing of parameters
        params = {p.get("Key"): p.get("Value") for p in params_list if isinstance(p, dict)}
        logger.info("Parsed parameters: %s", params)

        # Extract amount correctly
        amount = (
            params.get("TransactionAmount") or
            params.get("Amount")
        )

        receipt = params.get("TransactionReceipt")
        receiver_info = params.get("ReceiverPartyPublicName")

        if not amount:
            logger.warning("No amount found in B2C callback. Params: %s", params)
            return Response({"Result": "Acknowledged"})

        try:
            amount_val = Decimal(str(amount))
        except Exception:
            logger.error("Amount is not numeric: %s", amount)
            return Response({"Result": "Acknowledged"})

        # Extract phone safely
        phone_val = None
        if receiver_info:
            # Format: "254700123456 - John Doe"
            phone_val = ''.join(ch for ch in receiver_info if ch.isdigit())

        # --------------- MATCH WALLET TRANSACTION ------------------
        tx = None

        if phone_val:
            tx = WalletTransaction.objects.filter(
                type="withdraw",
                amount=amount_val,
                phone__endswith=phone_val
            ).last()

        if not tx and phone_val:
            tx = WalletTransaction.objects.filter(
                type="withdraw",
                phone__endswith=phone_val,
                status="pending"
            ).last()

        if not tx:
            tx = WalletTransaction.objects.filter(
                type="withdraw",
                amount=amount_val,
                status="pending"
            ).last()

        if not tx:
            logger.warning("No matching withdrawal for phone=%s amount=%s", phone_val, amount_val)
            return Response({"Result": "Received"})

        # ---------------- HANDLE SUCCESS / FAILURE ----------------
        if result_code == 0:
            tx.status = "success"
        else:
            tx.status = "failed"
            wallet = Wallet.objects.get(user=tx.user)
            wallet.balance += tx.amount
            wallet.save()

        tx.save()

    except Exception as e:
        logger.exception("B2C Callback Fatal Error: %s", e)

    return Response({"Result": "Received"})


# ---------------- FLUTTERWAVE DEPOSIT INITIATION ----------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def flutterwave_deposit(request):
    from .flutterwave import flutterwave_initialize_deposit

    amount = request.data.get("amount")
    if not amount:
        return Response({"error": "Amount required"}, status=400)

    flw = flutterwave_initialize_deposit(
        amount=amount,
        email=request.user.email,
        phone = request.data.get("phone"),
        name = request.user.get_full_name()
    )
    print("FLW RESPONSE:", flw)

    if flw.get("status") != "success" or not flw.get("data"):
        return Response({"error": flw.get("message", "Failed to initialize payment")}, status=400)

    data = flw["data"]

    WalletTransaction.objects.create(
        user=request.user,
        type="deposit",
        amount=Decimal(str(amount)),
        reference=flw["tx_ref"],
        status="pending",

)

    return Response({"payment_link": data["link"]})




def flutterwave_callback(request):
    """
    Redirect handler for Flutterwave payment redirect after checkout.

    Flutterwave redirects the payer here after payment attempt. This endpoint
    checks the transaction status and redirects back to the frontend with
    the payment result so the frontend can show a confirmation/error message.
    The authoritative webhook (flutterwave_webhook) updates wallet balances.
    """
    tx_ref = request.GET.get('tx_ref')
    status_param = request.GET.get('status', 'unknown')

    if not tx_ref:
        # No tx_ref; redirect to frontend with error
        return redirect('http://localhost:5173/wallet?payment_status=error&message=Missing+transaction+reference')

    # Look up the WalletTransaction to confirm it exists
    tx = WalletTransaction.objects.filter(reference=tx_ref).first()
    
    if not tx:
        return redirect(f'http://localhost:5173/wallet?payment_status=unknown&tx_ref={tx_ref}')

    # Build redirect URL with payment status and details
    # Frontend will use these query params to show confirmation or retry UI
    message = 'Payment successful - your wallet is being credited' if status_param.lower() == 'successful' else 'Payment failed or cancelled'
    
    return redirect(f'http://localhost:5173/wallet?payment_status={status_param}&tx_ref={tx_ref}&amount={tx.amount}&message={message}')


@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def flutterwave_withdraw(request):
    """Initiate a Flutterwave bank transfer withdrawal from user's wallet.

    Expected JSON: { amount, account_bank, account_number, account_name (optional), pin }
    """
    account_bank = request.data.get('account_bank')
    account_number = request.data.get('account_number')
    account_name = request.data.get('account_name')
    amount_str = request.data.get('amount')
    pin = request.data.get('pin')

    # Debug: log auth header + incoming payload to diagnose 401 Unauthorized
    try:
        auth_hdr = request.META.get('HTTP_AUTHORIZATION')
        logger.info("[FLW WITHDRAW] Authorization header: %s", auth_hdr)
        logger.info("[FLW WITHDRAW] request.user: %s authenticated=%s", getattr(request, 'user', None), getattr(request.user, 'is_authenticated', False))
        logger.info("[FLW WITHDRAW] incoming payload keys: %s", list(request.data.keys()) if hasattr(request, 'data') else 'no-data')
    except Exception:
        logger.exception('Failed to log withdraw debug info')

    if not pin:
        return Response({"error": "PIN required for withdrawal"}, status=400)

    # If the view reached here but request.user is not authenticated (401 occurred),
    # attempt manual JWT authentication to give clearer logs and allow dev testing
    try:
        if not getattr(request, 'user', None) or not getattr(request.user, 'is_authenticated', False):
            auth = JWTAuthentication()
            auth_result = auth.authenticate(request)
            if auth_result:
                request.user, _ = auth_result
                logger.info('[FLW WITHDRAW] Manually authenticated user via JWT: %s', request.user)
            else:
                logger.info('[FLW WITHDRAW] Manual JWT authenticate returned no result')
    except Exception:
        logger.exception('[FLW WITHDRAW] Manual JWT authentication failed')

    if not request.user.check_pin(pin):
        return Response({"error": "Invalid PIN"}, status=401)

    try:
        amount = Decimal(str(amount_str))
    except Exception:
        return Response({"error": "Invalid amount"}, status=400)

    wallet = Wallet.objects.get(user=request.user)
    if wallet.balance < amount:
        return Response({"error": "Insufficient balance"}, status=400)

    # Try to create beneficiary (optional) then initiate transfer
    try:
        # Validate required bank details
        if not account_bank or not account_number:
            return Response({"error": "account_bank and account_number are required"}, status=400)

        # Development fallback: when DEBUG=True, allow mocking transfers locally
        # This avoids Flutterwave's IP-whitelisting requirement during local testing.
        from django.conf import settings as _settings
        if getattr(_settings, 'DEBUG', False) and os.getenv('FLW_MOCK_TRANSFERS', '1') == '1':
            reference = str(uuid.uuid4())
            provider_res = {
                'status': 'success',
                'data': {'id': 'mock', 'reference': reference},
                'reference': reference
            }
            logger.info('[FLW WITHDRAW] Using MOCK provider_res (DEBUG) payload')
        else:
            # We can either create a beneficiary or transfer directly using bank details
            provider_res = initiate_transfer(
                amount=amount,
                account_bank=account_bank,
                account_number=account_number,
                narration=f"Wallet withdrawal for user {request.user.id}"
            )
    except Exception as e:
        logger.exception("Flutterwave transfer initiation failed: %s", e)
        # Return provider error details in DEBUG mode to help debugging locally
        from django.conf import settings as _settings
        if getattr(_settings, 'DEBUG', False):
            return Response({"error": "Failed to initiate transfer", "details": str(e)}, status=500)
        return Response({"error": "Failed to initiate transfer"}, status=500)

    # Use provider reference if available, otherwise create our own
    reference = provider_res.get('reference') or provider_res.get('data', {}).get('reference') or str(uuid.uuid4())

    # Deduct balance and create pending records
    try:
        with transaction.atomic():
            wallet.balance -= amount
            wallet.save()

            WalletTransaction.objects.create(
                user=request.user,
                phone=account_number,
                amount=amount,
                type='withdraw',
                status='pending',
                reference=reference
            )

            Transaction.objects.create(
                wallet=wallet,
                transaction_type='WITHDRAWAL',
                amount=amount,
                currency_from=getattr(wallet, 'currency', 'KES'),
                currency_to=getattr(wallet, 'currency', 'KES'),
                converted_amount=amount,
                status='PENDING',
                description=f'Flutterwave withdraw reference {reference} to {account_number}'
            )
    except Exception as e:
        logger.exception('Failed to create pending withdraw records: %s', e)
        return Response({"error": "Server error creating withdrawal record"}, status=500)

    payload = {
        'flutterwave_response': provider_res,
        'reference': reference,
        'wallet_balance': str(wallet.balance),
        'message': 'Withdrawal initiated — awaiting provider confirmation.'
    }

    return Response(payload)
