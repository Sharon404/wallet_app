import requests
import base64
import logging
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)

def generate_access_token():
    url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    try:
        response = requests.get(url, auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET), timeout=10)
        logger.info("MPesa token request: %s - status %s", url, response.status_code)
        data = response.json()
        if response.status_code != 200:
            logger.warning("Failed to get access token: %s", data)
            return None
        token = data.get('access_token')
        if not token:
            logger.warning("No access_token in response: %s", data)
            return None
        return token
    except Exception as e:
        logger.exception("Error generating M-Pesa access token: %s", e)
        return None


def generate_password():
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    data = settings.MPESA_SHORTCODE + settings.MPESA_PASSKEY + timestamp
    encoded = base64.b64encode(data.encode()).decode()
    return encoded, timestamp


def stk_push(phone, amount, account_reference="Wallet Deposit"):
    token = generate_access_token()
    if not token:
        return {"error": "Failed to generate access token"}

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

    try:
        logger.info("STK push payload: %s", payload)
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        logger.info("STK push response status: %s", response.status_code)
        try:
            data = response.json()
        except ValueError:
            data = {"error": "Invalid JSON in STK response", "text": response.text}
            logger.warning("Invalid JSON response from STK push: %s", response.text)
        logger.info("STK push response body: %s", data)

        # Return the parsed response or an error wrapper
        if response.status_code not in (200, 201):
            return {"error": "STK push failed", "status": response.status_code, "response": data}

        return data
    except requests.exceptions.RequestException as e:
        logger.exception("STK push request exception: %s", e)
        return {"error": str(e)}

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
            "Amount": int(amount),
            "PartyA": getattr(settings, 'MPESA_B2C_SHORTCODE', '600000'),
            "PartyB": phone,
            "Remarks": "Wallet Withdrawal",
            "QueueTimeOutURL": getattr(settings, 'MPESA_B2C_TIMEOUT_URL', 'https://dierdre-nondialyzing-asthmatically.ngrok-free.dev/api/mpesa/b2c/timeout/'),
            "ResultURL": getattr(settings, 'MPESA_B2C_RESULT_URL', 'https://dierdre-nondialyzing-asthmatically.ngrok-free.dev/api/mpesa/b2c/result/'),
            "Occasion": "withdrawal"
        }
        print("B2C Callback payload:", payload)

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
