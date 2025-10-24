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
from .models import Wallet, Transaction, OTP
from .serializers import (
    WalletSerializer,
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



User = get_user_model()


# ---------------- REGISTER ----------------
@api_view(['POST'])
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
    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email,
    })

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


# ---------------- TRANSFER ----------------
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
