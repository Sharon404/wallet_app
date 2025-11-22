from decimal import Decimal
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from django.contrib.auth import get_user_model, authenticate
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
from .models import Wallet, Transaction, OTP, CustomUser, CURRENCY_CHOICES
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

            if amount <= 0:
                return Response({'error': 'Positive amount is required.'}, status=400)

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

# All transaction types (transfer, withdraw, deposit) now handled by TransactionFlowView
# SendMoneyView and withdraw_and_send removed in favor of unified endpoint