from django.urls import path
from rest_framework.response import Response
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
    initiate_stk,
    get_stk_status,
    get_withdraw_status,
    mpesa_callback,
    withdraw_from_wallet,
    mpesa_b2c_result,
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
    path('mpesa/stk/', initiate_stk, name='initiate_stk'),
    path('mpesa/stk/status/', get_stk_status, name='mpesa_stk_status'),
    path('mpesa/withdraw/status/', get_withdraw_status, name='mpesa_withdraw_status'),
    path('mpesa/callback/', mpesa_callback, name='mpesa_callback'),
    path('mpesa/withdraw/', withdraw_from_wallet , name='mpesa_withdraw'),
    path("mpesa/b2c/result/", mpesa_b2c_result, name='mpesa_b2c_result'),
    path("mpesa/b2c/timeout/", lambda r: Response({"status": "timeout"}), name='mpesa_b2c_timeout'),


    # Authentication endpoints
    path('register/', register_user, name='register_user'),
    path('activate/<uidb64>/<token>/', activate_account, name='activate_account'),
    path('login/', login_user, name='login_user'),
    path('verify-otp/', verify_otp, name='verify_otp'),
]
