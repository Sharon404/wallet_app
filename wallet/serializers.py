from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Wallet, Transaction

# Get the custom user model
User = get_user_model()


# Serializer for existing users (read-only)
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'mobile']


# Serializer for registration (create user)
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    # require currency at registration (chosen when account is created)
    currency = serializers.ChoiceField(choices=[c[0] for c in Wallet._meta.get_field('currency').choices])

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'mobile', 'password', 'confirm_password', 'currency']

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        currency = validated_data.pop('currency', None)
        # Set a flag to prevent signal from creating a wallet
        from django.db.models.signals import post_save
        from .models import CustomUser, create_user_wallet
        post_save.disconnect(create_user_wallet, sender=CustomUser)
        try:
            user = User.objects.create_user(**validated_data)
            # create wallet with chosen currency
            if currency:
                Wallet.objects.create(user=user, currency=currency)
        finally:
            # Re-connect signal for other operations
            post_save.connect(create_user_wallet, sender=CustomUser)
        return user

# --- Login Serializer ---
class LoginSerializer(serializers.Serializer):
    username_or_email = serializers.CharField()
    password = serializers.CharField()


# --- OTP Verification Serializer ---
class VerifyOTPSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    otp = serializers.CharField(max_length=6)

    
# Wallet Serializer
class WalletSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Wallet
        fields = ['wallet_id', 'balance', 'currency', 'created_at', 'user']


# Transaction Serializer
class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'

class WithdrawSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency_to = serializers.ChoiceField(choices=[c[0] for c in Wallet._meta.get_field('currency').choices])
    receiver_email = serializers.EmailField()
    # optional: description, swift/bank details etc.