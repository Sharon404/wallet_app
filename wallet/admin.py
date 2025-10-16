from django.contrib import admin
from django.db.models import Sum, Q
from .models import Wallet, Transaction


# Allow viewing transactions under each wallet
class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    readonly_fields = ('transaction_id', 'transaction_type', 'amount', 'timestamp', 'description')


# Wallet admin
@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'wallet_id',
        'balance',
        'total_deposits',
        'total_withdrawals',
        'total_transfers',
        'created_at',
    )
    search_fields = ('user__username',)
    readonly_fields = ('wallet_id', 'created_at')
    inlines = [TransactionInline]

    def total_deposits(self, obj):
        total = obj.transactions.filter(transaction_type='DEPOSIT').aggregate(Sum('amount'))['amount__sum']
        return total or 0
    total_deposits.short_description = 'Total Deposits'

    def total_withdrawals(self, obj):
        total = obj.transactions.filter(transaction_type='WITHDRAWAL').aggregate(Sum('amount'))['amount__sum']
        return total or 0
    total_withdrawals.short_description = 'Total Withdrawals'

    def total_transfers(self, obj):
        total = obj.transactions.filter(transaction_type='TRANSFER').aggregate(Sum('amount'))['amount__sum']
        return total or 0
    total_transfers.short_description = 'Total Transfers'

    # Summary footer at bottom
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data['cl'].queryset
            response.context_data['summary'] = {
                'total_balance': qs.aggregate(Sum('balance'))['balance__sum'] or 0
            }
        except (AttributeError, KeyError):
            return response
        return response


# 