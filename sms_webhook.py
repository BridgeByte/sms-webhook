from flask import Flask, request, jsonify
import requests
from base64 import b64encode
import os

app = Flask(__name__)

# Credentials
client_id = os.environ.get("RC_CLIENT_ID")
client_secret = os.environ.get("RC_CLIENT_SECRET")
jwt_token = os.environ.get("RINGCENTRAL_JWT")
platform_url = 'https://platform.ringcentral.com'
sender_number = '+12014096774'
zoho_access_token = os.environ.get("ZOHO_ACCESS_TOKEN")

@app.route('/send-sms', methods=['POST'])
def send_sms():
    data = request.json
    print("📥 Incoming webhook data:", data)

    recipient_number = data.get('phone')
    lead_name = data.get('name', 'there')
    lead_id = data.get('id')
    lead_owner = data.get('owner', '').strip()

    if not recipient_number or not lead_id or not lead_owner:
        return jsonify({'error': 'Missing required lead data'}), 400

    message_text = f"""Hello {lead_name}, My name is Steven Bridge—an online specialist with Aurora.

I see that you’re interested in our kitchen deals. In order to better assist you:

May I know more about your kitchen project/goals?

https://auroracirc.com/"""

    # Step 1: Authenticate with RingCentral
    auth_url = f'{platform_url}/restapi/oauth/token'
    auth_headers = {
        'Authorization': 'Basic ' + b64encode(f'{client_id}:{client_secret}'.encode()).decode(),
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    auth_body = {
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': jwt_token
    }

    auth_response = requests.post(auth_url, headers=auth_headers, data=auth_body)
    access_token = auth_response.json().get('access_token')

    if not access_token:
        print("❌ RingCentral authentication failed:", auth_response.text)
        return jsonify({'error': 'Failed to authenticate with RingCentral'}), 500

    # Step 2: Send SMS
    sms_url = f'{platform_url}/restapi/v1.0/account/~/extension/~/sms'
    sms_headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    sms_body = {
        'from': {'phoneNumber': sender_number},
        'to': [{'phoneNumber': recipient_number}],
        'text': message_text
    }

    sms_response = requests.post(sms_url, headers=sms_headers, json=sms_body)

    if sms_response.status_code == 200:
        print("✅ SMS sent!")

        # Step 3: Update Zoho lead status
        if lead_owner.lower() == "steven bridgemohan":
            print("🔄 Updating Zoho lead status...")
            zoho_url = f"https://www.zohoapis.com/crm/v2/Leads/{lead_id}"
            zoho_headers = {
                "Authorization": f"Zoho-oauthtoken {zoho_access_token}",
                "Content-Type": "application/json"
            }
            zoho_body = {
                "data": [
                    {
                        "Lead_Status": "Attempted to Contact"
                    }
                ]
            }
            zoho_response = requests.put(zoho_url, headers=zoho_headers, json=zoho_body)

            if zoho_response.status_code == 200:
                print("✅ Zoho lead updated successfully!")
            else:
                print("❌ Zoho update failed:", zoho_response.text)

        return jsonify({'status': 'SMS sent and Zoho updated'}), 200
    else:
        print("❌ SMS FAILED:", sms_response.status_code, sms_response.text)
        return jsonify({'error': 'SMS failed'}), 403

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
