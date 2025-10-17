from django.contrib import admin
from django.template.response import TemplateResponse
from django.db.models import Sum
from .models import Wallet, Transaction
from django.contrib.auth.models import User, Group


class CustomAdminSite(admin.AdminSite):
    site_header = "Wallet System Admin"
    site_title = "Wallet Admin"
    index_title = "Dashboard Overview"

    # Override the default index (home) view
    def index(self, request, extra_context=None):
        total_wallets = Wallet.objects.count()
        total_balance = Wallet.objects.aggregate(Sum('balance'))['balance__sum'] or 0
        total_deposits = Transaction.objects.filter(transaction_type='DEPOSIT').aggregate(Sum('amount'))['amount__sum'] or 0
        total_withdrawals = Transaction.objects.filter(transaction_type='WITHDRAWAL').aggregate(Sum('amount'))['amount__sum'] or 0
        total_transfers = Transaction.objects.filter(transaction_type='TRANSFER').aggregate(Sum('amount'))['amount__sum'] or 0
        recent_transactions = Transaction.objects.select_related('wallet__user').order_by('-timestamp')[:5]

        context = dict(
            self.each_context(request),
            total_wallets=total_wallets,
            total_balance=total_balance,
            total_deposits=total_deposits,
            total_withdrawals=total_withdrawals,
            total_transfers=total_transfers,
            recent_transactions=recent_transactions,
        )

        if extra_context:
            context.update(extra_context)

        return TemplateResponse(request, "admin/dashboard.html", context)


# Instantiate your custom admin site
dashboard_admin_site = CustomAdminSite(name='dashboard_admin')

# Register models
dashboard_admin_site.register(User)
dashboard_admin_site.register(Group)
dashboard_admin_site.register(Wallet)
dashboard_admin_site.register(Transaction)
