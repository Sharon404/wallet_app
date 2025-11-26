from decimal import Decimal
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
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
from rest_framework import status
from .models import CustomUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from django.db import transaction
from .utils import convert_currency

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
        if response_code == '0' and ref:
            # create pending tx linked to the authenticated user
            try:
                from decimal import Decimal as _D
                amount_dec = _D(str(amount))
            except Exception:
                amount_dec = None

            # Use a unique reference, fallback to UUID
            tx_ref = ref or str(uuid.uuid4())

            # Only create if not already present
            if not WalletTransaction.objects.filter(reference=tx_ref).exists():
                WalletTransaction.objects.create(
                    user=request.user,
                    phone=phone,
                    amount=amount_dec or Decimal('0.00'),
                    type='deposit',
                    status='pending',
                    reference=tx_ref
                )
    except Exception:
        logger.exception('Failed to create pending WalletTransaction for STK push')

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

        amount = _get_item_value(callback_meta, name="Amount", idx=0)
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

        # Try to match an existing pending transaction by reference first (best
        # way to map a callback to a user). If found, use that transaction's
        # user and amount.
        tx_by_ref = None
        if reference:
            try:
                tx_by_ref = WalletTransaction.objects.filter(reference=reference).first()
                if tx_by_ref:
                    user = tx_by_ref.user
                    # prefer the amount on the transaction if present
                    try:
                        amount_val = tx_by_ref.amount if tx_by_ref.amount is not None else amount_val
                    except Exception:
                        pass
                    logger.info("Found pending WalletTransaction by reference %s -> user=%s amount=%s", reference, user, amount_val)
            except Exception:
                tx_by_ref = None

        # Try to find a user with matching mobile field only if we didn't find tx_by_ref
        user = None
        if (not tx_by_ref) and phone:
            # Normalize phone to a digits-only string
            try:
                phone_str = str(phone).strip()
            except Exception:
                phone_str = None

            if phone_str:
                digits = ''.join(ch for ch in phone_str if ch.isdigit())
            else:
                digits = None

            if not digits:
                lookup_candidates = set()
            else:
                lookup_candidates = set()
                lookup_candidates.add(digits)
                # Add variations: with/without leading +
                lookup_candidates.add(digits.lstrip('+'))

                # If starts with 0 (e.g., 07...), add 254 variant
                if digits.startswith('0') and not digits.startswith('254'):
                    lookup_candidates.add('254' + digits.lstrip('0'))
                # If starts with 254, add 0-prefixed variation
                if digits.startswith('254'):
                    lookup_candidates.add('0' + digits[3:])

                # Always add last-9 digits for fuzzy matching
                last9 = digits[-9:]
                lookup_candidates.add(last9)

            logger.info("STK callback phone normalization: raw=%s digits=%s candidates=%s", phone, digits, lookup_candidates)

            # search by mobile field
            from .models import CustomUser
            # Try exact/normalized matches first
            for p in list(lookup_candidates):
                try:
                    if not p:
                        continue
                    user = CustomUser.objects.filter(mobile=p).first()
                    if user:
                        logger.info("Matched user by mobile exact: %s -> %s", p, user)
                        break
                except Exception:
                    user = None

            # Fallback: last-9 digits matching
            if not user and digits:
                try:
                    last9 = digits[-9:]
                    user = CustomUser.objects.filter(mobile__endswith=last9).first()
                    if user:
                        logger.info("Matched user by mobile endswith last9: %s -> %s", last9, user)
                except Exception:
                    user = None

        if result_code == 0 and (user or tx_by_ref) and amount_val is not None:
            # credit wallet
            try:
                wallet, _ = Wallet.objects.get_or_create(user=user)
                wallet.balance += Decimal(amount_val)
                wallet.save()

                # If we matched a pending transaction, mark it successful and
                # reuse it. Otherwise create a new transaction with a unique reference.
                if tx_by_ref:
                    tx_by_ref.status = 'success'
                    tx_by_ref.amount = amount_val if (tx_by_ref.amount is None) else tx_by_ref.amount
                    tx_by_ref.phone = phone or tx_by_ref.phone
                    tx_by_ref.save()
                    logger.info('Updated existing WalletTransaction %s -> status success', tx_by_ref.reference)
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

                logger.info(f"Credited {amount_val} to {user}. Wallet new balance: {wallet.balance}")

            except Exception as e:
                logger.exception("Error crediting wallet on STK callback: %s", e)

        else:
            # create a failed/pending transaction only if we can identify a user
            try:
                ref = reference or (mpesa_receipt or f"none-{random.randint(100000,999999)}")
                if tx_by_ref:
                    tx_by_ref.status = 'failed'
                    tx_by_ref.amount = amount_val or tx_by_ref.amount or Decimal('0.00')
                    tx_by_ref.phone = phone or tx_by_ref.phone
                    tx_by_ref.save()
                    logger.info('Marked pending WalletTransaction %s as failed', tx_by_ref.reference)
                elif user:
                    WalletTransaction.objects.create(
                        user=user,
                        phone=phone,
                        amount=amount_val or Decimal('0.00'),
                        type="deposit",
                        status="failed",
                        reference=ref
                    )
                else:
                    logger.warning("STK callback received but could not find user for phone %s; skipping WalletTransaction creation", phone)
            except Exception as e:
                logger.exception("Error recording failed STK callback: %s", e)

    except Exception as e:
        logger.exception("Callback Error: %s", e)

    return Response({"Result": "Callback received"})


# ---------------- M-PESA WITHDRAWAL ----------------
@csrf_exempt
@api_view(["POST"])
def withdraw_from_wallet(request):
    phone = request.data.get("phone")
    amount_str = request.data.get("amount")  
    pin = request.data.get("pin")

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

    if res.get("ResponseCode") == "0":
        wallet.balance -= amount
        wallet.save()
        WalletTransaction.objects.create(
            user=request.user,
            type="withdraw",
            amount=amount,
            status="pending"   # update via callback
        )

    return Response(res)

# ---------------- M-PESA B2C RESULT CALLBACK ----------------
@csrf_exempt
@api_view(["POST"])
def mpesa_b2c_result(request):
    result = request.data

    try:
        result_code = result['Result']['ResultCode']
        phone = result['Result']['ResultParameters']['ResultParameter'][1]['Value']
        amount = result['Result']['ResultParameters']['ResultParameter'][0]['Value']

        tx = WalletTransaction.objects.filter(
            type="withdraw", amount=amount, phone=phone
        ).last()

        if result_code == 0:
            tx.status = "success"
        else:
            tx.status = "failed"
            # refund wallet
            wallet = Wallet.objects.get(user=tx.user)
            wallet.balance += tx.amount
            wallet.save()

        tx.save()

    except Exception as e:
        print("B2C Callback Error:", e)

    return Response({"Result": "Received"})
