import os
import aiohttp
import sys
from dotenv import load_dotenv
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# Load environment variables securely
load_dotenv()

# TextBee configuration
TEXTBEE_API_KEY = os.getenv("TEXTBEE_API_KEY")
TEXTBEE_DEVICE_ID = os.getenv("TEXTBEE_DEVICE_ID")
TEXTBEE_BASE_URL = "https://api.textbee.dev/api/v1"


async def send_textbee_sms(body: str, phone_number: str) -> bool:
    """Sends SMS via TextBee and returns True if successful, False if it failed."""
    if not all((TEXTBEE_API_KEY, TEXTBEE_DEVICE_ID)):
        print("[ERROR] TextBee SMS is not configured. Set TEXTBEE_API_KEY and TEXTBEE_DEVICE_ID in .env.")
        return False

    if not phone_number:
        print("[ERROR] No phone number provided for TextBee SMS.")
        return False

    print(f" [DEBUG] Sending SMS via TextBee to {phone_number}...")
    
    # FIX 1: The correct TextBee endpoint includes the Device ID in the URL
    url = f"https://api.textbee.dev/api/v1/gateway/devices/{TEXTBEE_DEVICE_ID}/sendSMS"
    
    # FIX 2: TextBee uses 'x-api-key' instead of 'Bearer' tokens
    headers = {
        "x-api-key": TEXTBEE_API_KEY,
        "Content-Type": "application/json"
    }
    
    #  FIX 3: TextBee expects 'recipients' as a list, not 'phoneNumber'
    payload = {
        "recipients": [phone_number],
        "message": body
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status in (200, 201):
                    print(f"[DEBUG] TextBee SMS sent successfully to {phone_number}!")
                    return True
                else:
                    error_text = await response.text()
                    print(f"[DEBUG] TextBee API Error {response.status}: {error_text}")
                    return False
    except Exception as e:
        print(f" [DEBUG] Python Error inside TextBee function: {str(e)}")
        return False