from decimal import Decimal
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from .models import Wallet, Transaction
from .serializers import WalletSerializer, TransactionSerializer
from django.contrib.auth.hashers import make_password
from rest_framework import status
from rest_framework.decorators import api_view

User = get_user_model()

@api_view(['POST'])
def register_user(request):
    first_name = request.data.get('first_name')
    last_name = request.data.get('last_name')
    username = request.data.get('username')
    email = request.data.get('email')
    mobile = request.data.get('mobile')
    password = request.data.get('password')
    confirm_password = request.data.get('confirm_password')

    if not username or not password or not confirm_password:
        return Response(
            {'error': 'Username, password, and confirm password are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    if password != confirm_password:
        return Response({'error': 'Passwords do not match.'},
                        status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username=username).exists():
        return Response(
            {'error': 'Username already exists.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = User.objects.create(
        first_name=first_name,
        last_name=last_name,
        username=username,
        mobile_number=mobile,
        email=email,
        password=make_password(password)
    )

    # Update wallet with mobile number
    wallet = user.wallet  # created automatically by signal
    wallet.mobile = mobile
    wallet.save()

    #wallet = Wallet.objects.create(user=user, balance=0)

    return Response({
        'message': 'User registered successfully!',
        'username': user.username,
        'wallet_id': user.wallet.id
    }, status=status.HTTP_201_CREATED)

class WalletView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        serializer = WalletSerializer(wallet)
        return Response(serializer.data)


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
