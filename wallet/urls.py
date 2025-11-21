from django.urls import path
from .views import (
    WalletView,
    DepositView,
    TransactionFlowView,
    convert_preview,
    currencies_list,
    register_user,
    activate_account,
    login_user,
    verify_otp,
    user_profile,
)

urlpatterns = [
    # Wallet endpoints
    path('user/profile/', user_profile, name='user-profile'),
    path('wallet/', WalletView.as_view(), name='wallet'),
    path('deposit/', DepositView.as_view(), name='deposit'),
    # Backwards-compatible routes mapped to unified transaction flow
    path('transfer/', TransactionFlowView.as_view(), name='transfer'),
    path('withdraw/', TransactionFlowView.as_view(), name='withdraw_and_send'),
    path('transaction/', TransactionFlowView.as_view(), name='transaction_flow'),
    path('convert-preview/', convert_preview, name='convert_preview'),
    path('currencies/', currencies_list, name='currencies_list'),

    # Authentication endpoints
    path('register/', register_user, name='register_user'),
    path('activate/<uidb64>/<token>/', activate_account, name='activate_account'),
    path('login/', login_user, name='login_user'),
    path('verify-otp/', verify_otp, name='verify_otp'),
]
