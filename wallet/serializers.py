from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Wallet, Transaction

# ✅ Use your CustomUser model dynamically
User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User  # ✅ now this points to your CustomUser model
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class WalletSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Wallet
        fields = ['wallet_id', 'balance', 'created_at', 'user']


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['transaction_id', 'transaction_type', 'amount', 'timestamp', 'description']
