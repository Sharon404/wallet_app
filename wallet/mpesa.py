import requests
import base64
from datetime import datetime
from django.conf import settings

def generate_access_token():
    url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET))
    return response.json()['access_token']


def generate_password():
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    data = settings.MPESA_SHORTCODE + settings.MPESA_PASSKEY + timestamp
    encoded = base64.b64encode(data.encode()).decode()
    return encoded, timestamp


def stk_push(phone, amount, account_reference="Wallet Deposit"):
    token = generate_access_token()
    password, timestamp = generate_password()

    url = f"{settings.MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest"
    
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": settings.MPESA_CALLBACK_URL,
        "AccountReference": account_reference,
        "TransactionDesc": "Wallet Funding"
    }

    response = requests.post(url, json=payload, headers=headers)
    return response.json()

#--- M-Pesa Withdrawal ---
def mpesa_withdraw(phone, amount):
    try:
        token = generate_access_token()

        url = f"{settings.MPESA_BASE_URL}/mpesa/b2c/v1/paymentrequest"
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "InitiatorName": getattr(settings, 'MPESA_B2C_INITIATOR_NAME', 'testapi'),
            "SecurityCredential": getattr(settings, 'MPESA_B2C_SECURITY_CREDENTIAL', 'Safaricom111!'),
            "CommandID": "BusinessPayment",
            "Amount": amount,
            "PartyA": getattr(settings, 'MPESA_B2C_SHORTCODE', '600000'),
            "PartyB": phone,
            "Remarks": "Wallet Withdrawal",
            "QueueTimeOutURL": getattr(settings, 'MPESA_B2C_TIMEOUT_URL', 'https://localhost/mpesa/b2c/timeout/'),
            "ResultURL": getattr(settings, 'MPESA_B2C_RESULT_URL', 'https://localhost/mpesa/b2c/result/'),
            "Occasion": "withdrawal"
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Request Exception: {e}")
        return {"error": str(e)}
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        return {"error": str(e)}
    except requests.exceptions.ConnectionError as e:
        print(f"Connection Error: {e}")
        return {"error": str(e)}
    except requests.exceptions.Timeout as e:
        print(f"Timeout Error: {e}")
        return {"error": str(e)}
    except Exception as e:
        print(f"General Exception: {e}")
        return {"error": str(e)}
