from flask import Flask, request, jsonify
import requests
from base64 import b64encode
import os

app = Flask(__name__)

# RingCentral credentials
client_id = os.environ.get("RC_CLIENT_ID")
client_secret = os.environ.get("RC_CLIENT_SECRET")
jwt_token = os.environ.get("RINGCENTRAL_JWT")
platform_url = 'https://platform.ringcentral.com'
sender_number = '+12014096774'

# Zoho credentials
zoho_client_id = os.environ.get("ZOHO_CLIENT_ID")
zoho_client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
zoho_refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN")

your_name = "Steven Bridgemohan"

def get_zoho_access_token():
    token_url = "https://accounts.zoho.com/oauth/v2/token"
    params = {
        'refresh_token': zoho_refresh_token,
        'client_id': zoho_client_id,
        'client_secret': zoho_client_secret,
        'grant_type': 'refresh_token'
    }
    response = requests.post(token_url, params=params)
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        print("❌ Failed to refresh Zoho token:", response.text)
        return None

@app.route('/send-sms', methods=['POST'])
def send_sms():
    data = request.json
    print("📥 Incoming webhook data:", data)

    phone = data.get('phone')
    name = data.get('name', 'there')
    email = data.get('email')
    owner = your_name  # Assume webhook is only sent for your leads

    if not phone or not email:
        return jsonify({'error': 'Missing phone or email'}), 400

    message_text = f"""Hello {name}, My name is Steven Bridge—an online specialist with Aurora.

I see that you’re interested in our kitchen deals. In order to better assist you:

May I know more about your kitchen project/goals?

https://auroracirc.com/"""

    # Authenticate with RingCentral
    auth_response = requests.post(
        f'{platform_url}/restapi/oauth/token',
        headers={
            'Authorization': 'Basic ' + b64encode(f'{client_id}:{client_secret}'.encode()).decode(),
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        data={
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion': jwt_token
        }
    )
    access_token = auth_response.json().get('access_token')
    if not access_token:
        print("❌ RC Auth failed:", auth_response.text)
        return jsonify({'error': 'RingCentral auth failed'}), 500

    # Send SMS
    sms_response = requests.post(
        f'{platform_url}/restapi/v1.0/account/~/extension/~/sms',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        },
        json={
            'from': {'phoneNumber': sender_number},
            'to': [{'phoneNumber': phone}],
            'text': message_text
        }
    )

    if sms_response.status_code != 200:
        print("❌ SMS failed:", sms_response.text)
        return jsonify({'error': 'SMS failed'}), 403

    print("✅ SMS sent successfully")

    # Get fresh Zoho token
    zoho_token = get_zoho_access_token()
    if not zoho_token:
        return jsonify({'warning': 'SMS sent, Zoho auth failed'}), 207

    # Search lead by email
    search_url = f'https://www.zohoapis.com/crm/v2/Leads/search?email={email}'
    search_response = requests.get(
        search_url,
        headers={'Authorization': f'Zoho-oauthtoken {zoho_token}'}
    )

    if search_response.status_code != 200:
        print("❌ Zoho search failed:", search_response.text)
        return jsonify({'warning': 'SMS sent, but Zoho search failed'}), 207

    records = search_response.json().get('data', [])
    if not records:
        print("⚠️ No lead found for email:", email)
        return jsonify({'warning': 'SMS sent, but no matching lead'}), 207

    lead_id = records[0]['id']

    # Update lead status
    update_url = f'https://www.zohoapis.com/crm/v2/Leads/{lead_id}'
    update_body = {
        "data": [
            {
                "Lead_Status": "Attempted to Contact"
            }
        ]
    }

    update_response = requests.put(
        update_url,
        headers={
            'Authorization': f'Zoho-oauthtoken {zoho_token}',
            'Content-Type': 'application/json'
        },
        json=update_body
    )

    if update_response.status_code == 200:
        print("✅ Lead status updated")
        return jsonify({'status': 'SMS sent & lead updated'}), 200
    else:
        print("⚠️ Update failed:", update_response.text)
        return jsonify({'warning': 'SMS sent, but Zoho update failed'}), 207


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
