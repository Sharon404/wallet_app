from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth import get_user_model
from .models import Wallet, Transaction
from .dashboard_admin import CustomAdminSite

# ✅ Get your CustomUser model
User = get_user_model()

# --- Custom User Admin Registration ---
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'mobile', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'mobile')
    ordering = ('username',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'mobile')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'mobile', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )

# --- Inline Transactions ---
class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    readonly_fields = (
        'transaction_id',
        'transaction_type',
        'amount',
        'timestamp',
        'description',
    )
    can_delete = False
    show_change_link = True


# --- Wallet Admin Customization ---
@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'wallet_id',
        'colored_balance',
        'total_deposits',
        'total_withdrawals',
        'total_transfers',
        'created_at',
    )
    search_fields = ('user__username', 'wallet_id')
    readonly_fields = ('wallet_id', 'created_at')
    list_filter = ('created_at',)
    inlines = [TransactionInline]

    def colored_balance(self, obj):
        color = 'green' if obj.balance > 0 else 'red'
        return format_html(f'<b style="color:{color};">Ksh {obj.balance:,.2f}</b>')
    colored_balance.short_description = 'Current Balance'

    def total_deposits(self, obj):
        total = obj.transactions.filter(transaction_type='DEPOSIT').aggregate(Sum('amount'))['amount__sum']
        return f'Ksh {total or 0:,.2f}'
    total_deposits.short_description = 'Total Deposits'

    def total_withdrawals(self, obj):
        total = obj.transactions.filter(transaction_type='WITHDRAWAL').aggregate(Sum('amount'))['amount__sum']
        return f'Ksh {total or 0:,.2f}'
    total_withdrawals.short_description = 'Total Withdrawals'

    def total_transfers(self, obj):
        total = obj.transactions.filter(transaction_type='TRANSFER').aggregate(Sum('amount'))['amount__sum']
        return f'Ksh {total or 0:,.2f}'
    total_transfers.short_description = 'Total Transfers'

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data['cl'].queryset
            total_balance = qs.aggregate(Sum('balance'))['balance__sum'] or 0
            response.context_data['summary'] = {
                'total_balance': f"Ksh {total_balance:,.2f}"
            }
        except (AttributeError, KeyError):
            return response
        return response


# --- Transaction Admin Customization ---
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_id',
        'wallet',
        'get_username',
        'transaction_type',
        'formatted_amount',
        'timestamp',
        'description',
    )
    list_filter = ('transaction_type', 'timestamp')
    search_fields = ('wallet__user__username', 'description', 'transaction_id')
    readonly_fields = ('transaction_id', 'timestamp')
    date_hierarchy = 'timestamp'

    def get_username(self, obj):
        return obj.wallet.user.username
    get_username.short_description = 'User'

    def formatted_amount(self, obj):
        color = 'green' if obj.transaction_type == 'DEPOSIT' else 'red' if obj.transaction_type == 'WITHDRAWAL' else '#555'
        return format_html(f'<b style="color:{color};">Ksh {obj.amount:,.2f}</b>')
    formatted_amount.short_description = 'Amount'


# --- Register custom admin site ---
custom_admin_site = CustomAdminSite(name='custom_admin')
custom_admin_site.register(Wallet)
custom_admin_site.register(Transaction)
custom_admin_site.register(User, CustomUserAdmin)
