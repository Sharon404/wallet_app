# wallet/flutterwave.py
import os, requests, uuid
from django.conf import settings

from wallet_backend.settings import FLW_SECRET_KEY

FLW_SECRET = os.getenv("FLW_SECRET_KEY", settings.FLW_SECRET_KEY)
FLW_BASE = "https://api.flutterwave.com/v3"


# ------------------------------------------------------------
# 1. Create Flutterwave Payment (for Card/Mpesa deposits)
# ------------------------------------------------------------
def flutterwave_initialize_deposit(amount, email, phone, tx_ref=None, redirect_url=None):
    tx_ref = tx_ref or str(uuid.uuid4())
    payload = {
        "tx_ref": tx_ref,
        "amount": str(amount),
        "currency": "KES",
        "redirect_url": redirect_url or settings.FLW_REDIRECT_URL,
        "customer": {
            "email": email,
            "phonenumber": phone,
            "name": ""
        },
        "meta": {"integration": "wallet_app"},
        "customizations": {"title": "Wallet deposit"}
    }

    headers = {"Authorization": f"Bearer {FLW_SECRET}"}
    resp = requests.post(f"{FLW_BASE}/payments", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()



# ------------------------------------------------------------
# 2. Create Beneficiary (Bank or Mpesa)
# ------------------------------------------------------------
def create_beneficiary(account_number, bank_code, name):
    url = f"{FLW_BASE}/beneficiaries"

    headers = {
        "Authorization": f"Bearer {FLW_SECRET}",
        "Content-Type": "application/json"
    }

    payload = {
        "account_number": account_number,
        "bank_code": bank_code,
        "name": name
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()



# ------------------------------------------------------------
# 3. Initiate Transfer to Bank or Mpesa
# ------------------------------------------------------------
def initiate_transfer(amount, account_bank, account_number, narration="Wallet Payout", beneficiary_id=None):
    url = f"{FLW_BASE}/transfers"

    tx_ref = str(uuid.uuid4())

    payload = {
        "account_bank": account_bank,           # Bank code or Mpesa code
        "account_number": account_number,       # Phone number for Mpesa
        "amount": amount,
        "currency": "KES",
        "narration": narration,
        "reference": tx_ref,
        "callback_url": settings.FLW_TRANSFER_CALLBACK_URL,
        "beneficiary": beneficiary_id
    }

    headers = {
        "Authorization": f"Bearer {FLW_SECRET}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()



# ------------------------------------------------------------
# 4. Verify Transfer
# ------------------------------------------------------------
def verify_transfer(transfer_id):
    url = f"{FLW_BASE}/transfers/{transfer_id}"

    headers = {
        "Authorization": f"Bearer {FLW_SECRET}"
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()



# ------------------------------------------------------------
# 5. Fetch Banks (for Kenya or any country)
# ------------------------------------------------------------
def fetch_kenyan_banks():
    url = f"{FLW_BASE}/banks/KE"

    headers = {
        "Authorization": f"Bearer {FLW_SECRET}"
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()
