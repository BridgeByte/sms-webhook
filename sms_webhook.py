from flask import Flask, request, jsonify
import requests
from base64 import b64encode
import os
import time
import traceback

app = Flask(__name__)

# RingCentral config
client_id = os.environ.get("RC_CLIENT_ID")
client_secret = os.environ.get("RC_CLIENT_SECRET")
platform_url = 'https://platform.ringcentral.com'
sender_number = '+12014096774'

# Zoho config
zoho_client_id = os.environ.get("ZOHO_CLIENT_ID")
zoho_client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
zoho_refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN")
zoho_access_token = None
zoho_token_expires_at = 0

# RC token storage
rc_token_store = {
    "access_token": None,
    "refresh_token": os.environ.get("RC_REFRESH_TOKEN"),
    "expires_at": 0
}

your_name = "Steven Bridgemohan"

def get_rc_token():
    if rc_token_store["access_token"] and time.time() < rc_token_store["expires_at"]:
        return rc_token_store["access_token"]

    auth = 'Basic ' + b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    res = requests.post(
        f'{platform_url}/restapi/oauth/token',
        headers={'Authorization': auth, 'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'grant_type': 'refresh_token',
            'refresh_token': rc_token_store["refresh_token"]
        }
    )
    if res.status_code == 200:
        j = res.json()
        rc_token_store.update({
            "access_token": j['access_token'],
            "refresh_token": j['refresh_token'],
            "expires_at": time.time() + int(j['expires_in']) - 60
        })
        return j['access_token']
    else:
        print("❌ RingCentral token refresh failed", res.text)
        raise Exception("RC token refresh failed")

def get_zoho_token():
    global zoho_access_token, zoho_token_expires_at
    if zoho_access_token and time.time() < zoho_token_expires_at:
        return zoho_access_token

    res = requests.post(
        'https://accounts.zoho.com/oauth/v2/token',
        data={
            'refresh_token': zoho_refresh_token,
            'client_id': zoho_client_id,
            'client_secret': zoho_client_secret,
            'grant_type': 'refresh_token'
        }
    )
    if res.status_code == 200:
        j = res.json()
        zoho_access_token = j['access_token']
        zoho_token_expires_at = time.time() + int(j['expires_in']) - 60
        return zoho_access_token
    else:
        print("❌ Zoho token refresh failed", res.text)
        raise Exception("Zoho token refresh failed")

@app.route('/send-sms', methods=['POST'])
def send_sms():
    try:
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

        print("📨 Sending SMS to:", phone)
        rc_token = get_rc_token()
        rc_response = requests.post(
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
        print("📤 SMS response:", rc_response.status_code, rc_response.text)

        if rc_response.status_code != 200:
            return jsonify({'error': 'SMS failed'}), 403

        # Update Zoho lead
        print("🔍 Searching Zoho lead for:", email)
        zoho_token = get_zoho_token()
        search = requests.get(
            f'https://www.zohoapis.com/crm/v2/Leads/search?email={email}',
            headers={'Authorization': f'Zoho-oauthtoken {zoho_token}'}
        )
        search_json = search.json()
        print("🔎 Zoho search result:", search.status_code, search_json)

        records = search_json.get('data')
        if not records:
            print("⚠️ No lead found for email:", email)
            return jsonify({'error': 'Lead not found in Zoho'}), 404

        lead_id = records[0]['id']
        update = requests.put(
            f'https://www.zohoapis.com/crm/v2/Leads/{lead_id}',
            headers={
                'Authorization': f'Zoho-oauthtoken {zoho_token}',
                'Content-Type': 'application/json'
            },
            json={"data": [{"Lead_Status": "Attempted to Contact"}]}
        )
        print("✅ Zoho update response:", update.status_code, update.text)

        if update.status_code == 200:
            return jsonify({'status': 'Text sent + Zoho updated'}), 200
        else:
            return jsonify({'warning': 'Text sent but Zoho update failed'}), 207

    except Exception as e:
        print("🔥 Exception occurred:")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
