from flask import Flask, request, jsonify
import requests
from base64 import b64encode
import os

app = Flask(__name__)

# Load credentials from environment variables
client_id = os.environ.get("RC_CLIENT_ID")
client_secret = os.environ.get("RC_CLIENT_SECRET")
jwt_token = os.environ.get("RINGCENTRAL_JWT")
platform_url = 'https://platform.ringcentral.com'
sender_number = '+12014096774'

zoho_access_token = os.environ.get("ZOHO_ACCESS_TOKEN")
your_name = "Steven Bridgemohan"  # Only send/update if this is the lead owner

@app.route('/send-sms', methods=['POST'])
def send_sms():
    data = request.json
    print("📥 Incoming webhook data:", data)

    phone = data.get('phone')
    name = data.get('name', 'there')
    email = data.get('email')
    owner = data.get('owner')

    if not phone or not email:
        return jsonify({'error': 'Missing phone or email'}), 400

    if owner != your_name:
        print(f"⏭️ Lead is not assigned to {your_name}, skipping.")
        return jsonify({'skipped': 'Lead not assigned to you'}), 200

    message_text = f"""Hello {name}, My name is Steven Bridge—an online specialist with Aurora.

I see that you’re interested in our kitchen deals. In order to better assist you:

May I know more about your kitchen project/goals?

https://auroracirc.com/"""

    # Authenticate RingCentral
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

    # Search Zoho lead by email
    search_url = f'https://www.zohoapis.com/crm/v2/Leads/search?email={email}'
    search_response = requests.get(
        search_url,
        headers={'Authorization': f'Zoho-oauthtoken {zoho_access_token}'}
    )

    if search_response.status_code != 200:
        print("❌ Zoho search failed:", search_response.text)
        return jsonify({'error': 'Zoho search failed'}), 500

    records = search_response.json().get('data', [])
    if not records:
        print("⚠️ No Zoho lead found for email:", email)
        return jsonify({'error': 'No lead found in Zoho'}), 404

    lead_id = records[0]['id']

    # Update lead status to "Attempted to Contact"
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
            'Authorization': f'Zoho-oauthtoken {zoho_access_token}',
            'Content-Type': 'application/json'
        },
        json=update_body
    )

    if update_response.status_code == 200:
        print("✅ Zoho lead status updated")
        return jsonify({'status': 'SMS sent & lead status updated'}), 200
    else:
        print("⚠️ Zoho update failed:", update_response.text)
        return jsonify({'warning': 'SMS sent, but Zoho update failed'}), 207

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
