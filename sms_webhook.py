from flask import Flask, request, jsonify
import requests
from base64 import b64encode
import os
import time
import traceback

app = Flask(__name__)

# RingCentral credentials from environment
client_id = os.environ.get("RC_CLIENT_ID")
client_secret = os.environ.get("RC_CLIENT_SECRET")
rc_refresh_token = os.environ.get("RC_REFRESH_TOKEN")
platform_url = 'https://platform.ringcentral.com'
sender_number = '+12014096774'
rc_access_token = None

# Zoho credentials from environment
zoho_client_id = os.environ.get("ZOHO_CLIENT_ID")
zoho_client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
zoho_refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN")
zoho_access_token = None
zoho_token_expires_at = 0
your_name = os.environ.get("YOUR_NAME", "Steven Bridgemohan")

def refresh_rc_token():
    global rc_access_token, rc_refresh_token
    auth_header = 'Basic ' + b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    response = requests.post(
        f'{platform_url}/restapi/oauth/token',
        headers={
            'Authorization': auth_header,
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        data={
            'grant_type': 'refresh_token',
            'refresh_token': rc_refresh_token
        }
    )
    if response.status_code == 200:
        data = response.json()
        rc_access_token = data['access_token']
        rc_refresh_token = data['refresh_token']
        print("✅ RC token refreshed successfully.")
        return rc_access_token
    else:
        print("❌ RC token refresh failed:", response.status_code)
        print(response.text)
        raise Exception("RC auth error")

def refresh_zoho_token():
    global zoho_access_token, zoho_token_expires_at
    if zoho_access_token and time.time() < zoho_token_expires_at:
        return zoho_access_token

    response = requests.post(
        'https://accounts.zoho.com/oauth/v2/token',
        data={
            'refresh_token': zoho_refresh_token,
            'client_id': zoho_client_id,
            'client_secret': zoho_client_secret,
            'grant_type': 'refresh_token'
        }
    )
    if response.status_code == 200:
        data = response.json()
        zoho_access_token = data['access_token']
        zoho_token_expires_at = time.time() + int(data['expires_in']) - 60
        print("✅ Zoho token refreshed successfully.")
        return zoho_access_token
    else:
        print("❌ Zoho token refresh failed:", response.status_code)
        print(response.text)
        raise Exception("Zoho auth error")

@app.route('/send-sms', methods=['POST'])
def send_sms():
    data = request.json
    print("📥 Webhook received:", data)

    phone = data.get('phone')
    name = data.get('name', 'there')
    email = data.get('email')
    owner = data.get('owner')

    if not phone or not email:
        print("❌ Missing phone or email.")
        return jsonify({'error': 'Missing phone/email'}), 400

    if owner != your_name:
        print(f"⏭️ Lead not assigned to {your_name}, skipping.")
        return jsonify({'skipped': 'Lead not yours'}), 200

    message = f"""Hello {name}, My name is Steven Bridge—an online specialist with Aurora.

I see that you’re interested in our kitchen deals. In order to better assist you:

May I know more about your kitchen project/goals?

https://auroracirc.com/"""

    try:
        rc_token = refresh_rc_token()
        sms_response = requests.post(
            f'{platform_url}/restapi/v1.0/account/~/extension/~/sms',
            headers={
                'Authorization': f'Bearer {rc_token}',
                'Content-Type': 'application/json'
            },
            json={
                'from': {'phoneNumber': sender_number},
                'to': [{'phoneNumber': phone}],
                'text': message
            }
        )
        print("📤 SMS response:", sms_response.status_code, sms_response.text)
        if sms_response.status_code != 200:
            return jsonify({'error': 'SMS failed'}), 403
    except Exception as e:
        print("❌ Exception sending SMS:", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

    try:
        zoho_token = refresh_zoho_token()
        search = requests.get(
            f'https://www.zohoapis.com/crm/v2/Leads/search?email={email}',
            headers={'Authorization': f'Zoho-oauthtoken {zoho_token}'}
        )
        lead_data = search.json().get('data', [{}])[0]
        if not lead_data:
            return jsonify({'error': 'No Zoho match'}), 404

        lead_id = lead_data['id']
        update = requests.put(
            f'https://www.zohoapis.com/crm/v2/Leads/{lead_id}',
            headers={
                'Authorization': f'Zoho-oauthtoken {zoho_token}',
                'Content-Type': 'application/json'
            },
            json={"data": [{"Lead_Status": "Attempted to Contact"}]}
        )
        if update.status_code == 200:
            return jsonify({'status': 'Text sent + Zoho updated'}), 200
        else:
            return jsonify({'warning': 'Text sent but Zoho update failed'}), 207

    except Exception as e:
        print("❌ Zoho update failed:", e)
        traceback.print_exc()
        return jsonify({'error': 'Zoho error', 'details': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
