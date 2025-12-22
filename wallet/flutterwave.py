# wallet/flutterwave.py
import os
import uuid
import requests
from django.conf import settings

FLW_SECRET = os.getenv("FLW_SECRET_KEY", settings.FLW_SECRET_KEY)
FLW_BASE = "https://api.flutterwave.com/v3"

HEADERS = {
    "Authorization": f"Bearer {FLW_SECRET}",
    "Content-Type": "application/json"
}

# ------------------------------------------------------------
# 1. Initialize Deposit (Card / Mpesa)
# ------------------------------------------------------------
def initialize_deposit(amount, email, phone, name="", tx_ref=None, redirect_url=None):
    tx_ref = tx_ref or str(uuid.uuid4())

    payload = {
        "tx_ref": tx_ref,
        "amount": str(amount),
        "currency": "KES",
        "redirect_url": redirect_url or settings.FLW_REDIRECT_URL,
        "customer": {
            "email": email,
            "phonenumber": phone,
            "name": name or "Customer"
        },
        "meta": {"service": "wallet"},
        "customizations": {"title": "Wallet Deposit"}
    }

    resp = requests.post(
        f"{FLW_BASE}/payments",
        json=payload,
        headers=HEADERS,
        timeout=30
    )
    resp.raise_for_status()

    data = resp.json()
    data["tx_ref"] = tx_ref
    return data


def flutterwave_initialize_deposit(amount, email, phone, name="", tx_ref=None, redirect_url=None):
    """Backward-compatible wrapper expected by views."""
    return initialize_deposit(amount, email, phone, name=name, tx_ref=tx_ref, redirect_url=redirect_url)


# ------------------------------------------------------------
# 2. Initiate Withdrawal (Bank or Mpesa)
# ------------------------------------------------------------
def initiate_withdrawal(amount, account_bank, account_number, narration="Wallet Withdrawal", reference=None):
    reference = reference or str(uuid.uuid4())

    payload = {
        "account_bank": account_bank,
        "account_number": account_number,
        "amount": str(amount),
        "currency": "KES",
        "narration": narration,
        "reference": reference,
        "debit_currency": "KES"
    }

    resp = requests.post(
        f"{FLW_BASE}/transfers",
        json=payload,
        headers=HEADERS,
        timeout=30
    )
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError:
        try:
            err = resp.json()
        except Exception:
            err = {"status_code": resp.status_code, "text": resp.text}
        err["payload_sent"] = payload
        raise Exception(f"Flutterwave transfer error: {err}")

    data = resp.json()
    data["reference"] = reference
    return data


def create_beneficiary(account_bank, account_number, account_name="Recipient"):
    """Create a beneficiary in Flutterwave. Returns provider response."""
    payload = {
        "type": "bank_account",
        "name": account_name,
        "account_number": str(account_number),
        "bank_code": str(account_bank),
        "currency": "KES",
    }

    resp = requests.post(
        f"{FLW_BASE}/beneficiaries",
        json=payload,
        headers=HEADERS,
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()


def initiate_transfer(beneficiary_code=None, amount=None, account_bank=None, account_number=None, narration="Wallet Withdrawal", reference=None):
    """Initiate a transfer either using a beneficiary code or raw bank details.

    Returns provider response JSON. Uses the transfers endpoint.
    """
    reference = reference or str(uuid.uuid4())

    payload = {
        "amount": str(amount),
        "currency": "KES",
        "reference": reference,
        "narration": narration,
    }

    if beneficiary_code:
        payload["beneficiary"] = beneficiary_code
    else:
        # Use account_bank/account_number for one-off transfers
        payload.update({
            "account_bank": str(account_bank),
            "account_number": str(account_number),
            # debit_currency optional
        })

    resp = requests.post(
        f"{FLW_BASE}/transfers",
        json=payload,
        headers=HEADERS,
        timeout=30
    )
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError:
        # Try to return the JSON error body to aid debugging
        try:
            err = resp.json()
        except Exception:
            err = {"status_code": resp.status_code, "text": resp.text}
        # Attach original payload for diagnosis
        err["payload_sent"] = payload
        raise Exception(f"Flutterwave transfer error: {err}")

    data = resp.json()
    data["reference"] = reference
    return data


# ------------------------------------------------------------
# 3. Verify Withdrawal
# ------------------------------------------------------------
def verify_withdrawal(transfer_id):
    resp = requests.get(
        f"{FLW_BASE}/transfers/{transfer_id}",
        headers=HEADERS,
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()


# ------------------------------------------------------------
# 4. Fetch Banks by Country
# ------------------------------------------------------------
def fetch_banks(country_code="KE"):
    resp = requests.get(
        f"{FLW_BASE}/banks/{country_code}",
        headers=HEADERS,
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()
