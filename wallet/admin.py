from django.contrib import admin
from .models import Wallet, Transaction


# Allow viewing transactions under each wallet
class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    readonly_fields = ('transaction_id', 'transaction_type', 'amount', 'timestamp', 'description')


# Wallet admin
@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'wallet_id', 'balance', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('wallet_id', 'created_at')
    inlines = [TransactionInline]


# Transaction admin
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'wallet', 'transaction_type', 'amount', 'timestamp', 'description')
    list_filter = ('transaction_type',)
    search_fields = ('wallet__user__username', 'description')
    readonly_fields = ('transaction_id', 'timestamp')
