from django.apps import AppConfig


class WalletConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    # Use the full dotted path to the app package so Django registers the
    # correct application when INSTALLED_APPS contains 'wallet_app.wallet'.
    name = 'wallet_app.wallet'
