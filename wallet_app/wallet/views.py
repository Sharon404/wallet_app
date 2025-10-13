from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth.models import User
from .models import Wallet, Transaction
from .serializers import WalletSerializer, TransactionSerializer

class WalletView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet = Wallet.objects.get(user=request.user)
        serializer = WalletSerializer(wallet)
        return Response(serializer.data)


class DepositView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        amount = float(request.data.get('amount', 0))
        wallet = Wallet.objects.get(user=request.user)
        wallet.balance += amount
        wallet.save()

        Transaction.objects.create(
            wallet=wallet,
            transaction_type='DEPOSIT',
            amount=amount,
            description='Deposit added'
        )
        return Response({'message': 'Deposit successful', 'new_balance': wallet.balance})


class TransferView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        recipient_username = request.data.get('recipient')
        amount = float(request.data.get('amount', 0))
        sender_wallet = Wallet.objects.get(user=request.user)

        try:
            recipient_user = User.objects.get(username=recipient_username)
            recipient_wallet = Wallet.objects.get(user=recipient_user)
        except User.DoesNotExist:
            return Response({'error': 'Recipient not found'}, status=400)

        if sender_wallet.balance < amount:
            return Response({'error': 'Insufficient balance'}, status=400)

        # Transfer logic
        sender_wallet.balance -= amount
        recipient_wallet.balance += amount
        sender_wallet.save()
        recipient_wallet.save()

        # Record transactions
        Transaction.objects.create(wallet=sender_wallet, transaction_type='TRANSFER', amount=amount,
                                   description=f'Sent to {recipient_username}')
        Transaction.objects.create(wallet=recipient_wallet, transaction_type='TRANSFER', amount=amount,
                                   description=f'Received from {request.user.username}')

        return Response({'message': 'Transfer successful', 'new_balance': sender_wallet.balance})
