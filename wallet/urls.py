from django.urls import path
from .views import (
    WalletView,
    DepositView,
    TransferView,
    register_user,
    activate_account,
    login_user,
    verify_otp,
    login_user
)

urlpatterns = [
    # Wallet endpoints
    path('wallet/', WalletView.as_view(), name='wallet'),
    path('deposit/', DepositView.as_view(), name='deposit'),
    path('transfer/', TransferView.as_view(), name='transfer'),

    # Authentication endpoints
    path('register/', register_user, name='register_user'),
    path('activate/<uidb64>/<token>/', activate_account, name='activate_account'),
    path('login/', login_user, name='login_user'),
    path('verify-otp/', verify_otp, name='verify_otp'),
]
