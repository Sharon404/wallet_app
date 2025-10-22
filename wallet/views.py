from decimal import Decimal
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from django.contrib.auth import get_user_model, authenticate
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.contrib.auth.hashers import make_password
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Wallet, Transaction
from .serializers import (
    WalletSerializer,
    TransactionSerializer,
    RegisterSerializer,
    LoginSerializer,
    VerifyOTPSerializer
)
from .utils import send_activation_email, send_otp

User = get_user_model()


# REGISTER USER — sends activation email
@api_view(['POST'])
def register_user(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save(is_active=False)  # user inactive until activation
        send_activation_email(user, request)
        return Response({
            'message': 'Registration successful! Please check your email to activate your account.'
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



# ACTIVATE ACCOUNT — via email link
@api_view(['GET'])
def activate_account(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except Exception:
        return Response({'error': 'Invalid activation link.'}, status=status.HTTP_400_BAD_REQUEST)

    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        return Response({'message': 'Account activated successfully! You can now log in.'})
    else:
        return Response({'error': 'Activation link invalid or expired.'}, status=status.HTTP_400_BAD_REQUEST)



# LOGIN — username or email, sends OTP
@api_view(['POST'])
def login_user(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        username_or_email = serializer.validated_data['username_or_email']
        password = serializer.validated_data['password']

        user = authenticate(request, username=username_or_email, password=password)
        if user is not None:
            send_otp(user)
            return Response({'message': 'Login successful. OTP sent to your email.', 'user_id': user.id})
        else:
            return Response({'error': 'Invalid credentials or account not activated.'}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



# VERIFY OTP — final step before landing page
@api_view(['POST'])
def verify_otp(request):
    serializer = VerifyOTPSerializer(data=request.data)
    if serializer.is_valid():
        user_id = serializer.validated_data['user_id']
        otp = serializer.validated_data['otp']
        cached_otp = cache.get(f"otp_{user_id}")

        if cached_otp == otp:
            cache.delete(f"otp_{user_id}")
            return Response({'message': 'OTP verified successfully! Redirecting to landing page...'})
        else:
            return Response({'error': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# LOGIN VIEW — username or email + password
@api_view(['POST'])
def login_user(request):
    username_or_email = request.data.get('username_or_email')
    password = request.data.get('password')

    if not username_or_email or not password:
        return Response({'error': 'Username/Email and password are required.'}, status=400)

    # Try to authenticate with username or email
    user = authenticate(username=username_or_email, password=password)

    # If not found by username, try by email
    if user is None:
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user_obj = User.objects.get(email=username_or_email)
            user = authenticate(username=user_obj.username, password=password)
        except User.DoesNotExist:
            return Response({'error': 'Invalid login credentials.'}, status=400)

    # Check if user exists and is active
    if user is None:
        return Response({'error': 'Invalid username or password.'}, status=400)

    if not user.is_active:
        return Response({'error': 'Please activate your account via email first.'}, status=403)

    # If all good, log them in
    return Response({
        'message': 'Login successful!',
        'username': user.username,
        'email': user.email,
        'wallet_id': user.wallet.wallet_id
    }, status=200)


# WALLET VIEW — shows balance and details
class WalletView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        serializer = WalletSerializer(wallet)
        return Response(serializer.data)


# DEPOSIT VIEW — add funds to wallet
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



# TRANSFER VIEW
class TransferView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            recipient_username = request.data.get('recipient')
            amount = Decimal(request.data.get('amount', '0'))
            if amount <= 0:
                return Response({'error': 'Amount must be greater than zero'}, status=400)

            sender_wallet, _ = Wallet.objects.get_or_create(user=request.user)

            try:
                recipient_user = User.objects.get(username=recipient_username)
                recipient_wallet, _ = Wallet.objects.get_or_create(user=recipient_user)
            except User.DoesNotExist:
                return Response({'error': 'Recipient not found'}, status=400)

            if sender_wallet.balance < amount:
                return Response({'error': 'Insufficient balance'}, status=400)

            # Perform transfer
            sender_wallet.balance -= amount
            recipient_wallet.balance += amount
            sender_wallet.save()
            recipient_wallet.save()

            # Record transactions
            Transaction.objects.create(
                wallet=sender_wallet,
                transaction_type='TRANSFER',
                amount=amount,
                description=f'Sent to {recipient_username}'
            )
            Transaction.objects.create(
                wallet=recipient_wallet,
                transaction_type='TRANSFER',
                amount=amount,
                description=f'Received from {request.user.username}'
            )

            return Response({
                'message': 'Transfer successful',
                'sender_balance': str(sender_wallet.balance)
            })

        except Exception as e:
            return Response({'error': str(e)}, status=500)
