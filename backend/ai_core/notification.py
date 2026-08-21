import os
import base64
import aiohttp
import sys
from dotenv import load_dotenv
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# Load environment variables securely
load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
YOUR_VERIFIED_NUMBER = os.getenv("TWILIO_VERIFIED_NUMBER")

async def send_twilio_sms(body: str) -> bool:
    """Sends SMS and returns True if successful, False if it failed."""
    if not all((TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, YOUR_VERIFIED_NUMBER)):
        print("[ERROR] Twilio SMS is not configured. Set all TWILIO_* variables in .env.")
        return False

    print("🚀 [DEBUG] Starting secure send_twilio_sms...")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    
    credentials = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {"Authorization": f"Basic {encoded_credentials}"}
    
    payload = {
        "To": YOUR_VERIFIED_NUMBER,
        "From": TWILIO_PHONE_NUMBER,
        "Body": body  # Keep this equal to your approved template when using a Twilio trial account.
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=payload) as response:
                if response.status in (200, 201):
                    print("✅ [DEBUG] Twilio SMS sent successfully!")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ [DEBUG] Twilio API Error {response.status}: {error_text}")
                    return False
    except Exception as e:
        print(f"🔥 [DEBUG] Python Error inside Twilio function: {str(e)}")
        return False


async def send_twilio_sms_to_patient(body: str, phone_number: str) -> bool:
    """Sends SMS to patient's phone number and returns True if successful."""
    if not all((TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)):
        print("[ERROR] Twilio SMS is not configured. Set all TWILIO_* variables in .env.")
        return False

    if not phone_number:
        print("[ERROR] No phone number provided for patient SMS.")
        return False

    print(f"🚀 [DEBUG] Sending emergency SMS to {phone_number}...")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    
    credentials = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {"Authorization": f"Basic {encoded_credentials}"}
    
    payload = {
        "To": phone_number,
        "From": TWILIO_PHONE_NUMBER,
        "Body": body
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=payload) as response:
                if response.status in (200, 201):
                    print(f"✅ [DEBUG] Emergency SMS sent successfully to {phone_number}!")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ [DEBUG] Twilio API Error {response.status}: {error_text}")
                    return False
    except Exception as e:
        print(f"🔥 [DEBUG] Python Error sending patient SMS: {str(e)}")
        return False
