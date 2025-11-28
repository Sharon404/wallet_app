"""
URL configuration for wallet_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from wallet.dashboard_admin import dashboard_admin_site 
from wallet.views import mpesa_b2c_result
from rest_framework.response import Response as DRFResponse
from django.http import HttpResponseRedirect
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# No rlpatterns variable needed — define urlpatterns below.

urlpatterns = [
   # path('admin/', admin.site.urls),
    # Redirect root URL to the API index so visiting '/' doesn't 404.
    path('', lambda request: HttpResponseRedirect('/api/')),
    # Support M-Pesa callbacks that POST to the root (no /api prefix). Some
    # providers (or test setups using ngrok) send callbacks to `/mpesa/...`.
    # Map those root paths directly to the same views so callbacks don't 404.
    path('mpesa/b2c/result/', mpesa_b2c_result),
    path('mpesa/b2c/timeout/', lambda r: DRFResponse({"status": "timeout"})),
    # Include the app's URLs. The app lives at the project root as `wallet`.
    path('api/', include('wallet.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('admin/', dashboard_admin_site.urls),
]
