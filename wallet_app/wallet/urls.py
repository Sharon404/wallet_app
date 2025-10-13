from django.urls import path
from .views import WalletView, DepositView, TransferView

urlpatterns = [
    path('wallet/', WalletView.as_view(), name='wallet'),
    path('deposit/', DepositView.as_view(), name='deposit'),
    path('transfer/', TransferView.as_view(), name='transfer'),
]
