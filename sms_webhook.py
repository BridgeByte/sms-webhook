from flask import Flask, request, jsonify
import requests
from base64 import b64encode

app = Flask(__name__)

# RingCentral credentials
client_id = os.environ.get("RC_CLIENT_ID")
client_secret = os.environ.get("RC_CLIENT_SECRET")
jwt_token = os.environ.get("RINGCENTRAL_JWT")

@app.route('/send-sms', methods=['POST'])
def send_sms():
    data = request.json
    print("📥 Incoming webhook data:", data)

    recipient_number = data.get('phone')
    lead_name = data.get('name', 'there')

    if not recipient_number:
        return jsonify({'error': 'Missing phone number'}), 400

    message_text = f"""Hello {lead_name}, My name is Steven Bridge—an online specialist with Aurora.

I see that you’re interested in our kitchen deals. In order to better assist you:

May I know more about your kitchen project/goals?

https://auroracirc.com/"""

    # Authenticate
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
        print("❌ Authentication failed:", auth_response.text)
        return jsonify({'error': 'Failed to authenticate'}), 500

    # Send SMS
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
        return jsonify({'status': 'SMS sent successfully!'}), 200
    else:
        print("❌ SMS FAILED:", sms_response.status_code, sms_response.text)
        return jsonify({'error': sms_response.text}), 403

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

