from flask import Flask, request, jsonify
import requests
from base64 import b64encode
import os
import time

app = Flask(__name__)

# Environment Config
client_id = os.environ.get("RC_CLIENT_ID")
client_secret = os.environ.get("RC_CLIENT_SECRET")
platform_url = 'https://platform.ringcentral.com'
sender_number = '+12014096774'

zoho_client_id = os.environ.get("ZOHO_CLIENT_ID")
zoho_client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
zoho_refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN")
your_name = os.environ.get("YOUR_NAME")

# Token Caches
rc_token_store = {
    "access_token": None,
    "refresh_token": os.environ.get("RC_REFRESH_TOKEN"),
    "expires_at": 0
}

zoho_access_token = None
zoho_token_expires_at = 0

def get_rc_token():
    if rc_token_store["access_token"] and time.time() < rc_token_store["expires_at"]:
        return rc_token_store["access_token"]

    auth = 'Basic ' + b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    res = requests.post(
        f'{platform_url}/restapi/oauth/token',
        headers={'Authorization': auth, 'Content-Type': 'application/x-www-form-urlencoded'},
        data={'grant_type': 'refresh_token', 'refresh_token': rc_token_store["refresh_token"]}
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
        raise Exception("RC auth error")

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
        raise Exception("Zoho auth error")

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

        print("📨 Sending SMS...")
        rc_token = get_rc_token()
        message = f"""Hello {name}, My name is Steven Bridge—an online specialist with Aurora.\n\nI see that you’re interested in our kitchen deals. In order to better assist you:\n\nMay I know more about your kitchen project/goals?\n\nhttps://auroracirc.com/"""

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

        print("📤 SMS status:", sms_response.status_code)
        print("📤 SMS response:", sms_response.text)

        if sms_response.status_code != 200:
            return jsonify({'error': 'SMS failed'}), 403

        zoho_token = get_zoho_token()
        search = requests.get(
            f'https://www.zohoapis.com/crm/v2/Leads/search?email={email}',
            headers={'Authorization': f'Zoho-oauthtoken {zoho_token}'}
        )
        lead = search.json().get('data', [{}])[0]
        if not lead:
            return jsonify({'error': 'No Zoho match'}), 404

        lead_id = lead['id']
        update = requests.put(
            f'https://www.zohoapis.com/crm/v2/Leads/{lead_id}',
            headers={
                'Authorization': f'Zoho-oauthtoken {zoho_token}',
                'Content-Type': 'application/json'
            },
            json={"data": [{"Lead_Status": "Attempted to Contact"}]}
        )

        print("📝 Zoho update status:", update.status_code)
        print("📝 Zoho update response:", update.text)

        if update.status_code == 200:
            return jsonify({'status': 'SMS sent + Zoho updated'}), 200
        else:
            return jsonify({'warning': 'Text sent but Zoho update failed'}), 207

    except Exception as e:
        print("💥 Unhandled Exception:", str(e))
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
