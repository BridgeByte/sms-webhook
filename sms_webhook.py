from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timedelta

app = Flask(__name__)

@app.route("/", methods=["GET"])
def health_check():
    return "✅ Flask is running"

# --- RingCentral JWT Token Management ---
ringcentral_token_data = {
    "access_token": None,
    "expires_at": None
}

def get_ringcentral_token():
    if ringcentral_token_data["access_token"] and datetime.now() < ringcentral_token_data["expires_at"]:
        return ringcentral_token_data["access_token"]

    url = "https://platform.ringcentral.com/restapi/oauth/token"
    auth = (os.environ['RC_CLIENT_ID'], os.environ['RC_CLIENT_SECRET'])
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": os.environ['RC_JWT']
    }

    response = requests.post(url, headers=headers, auth=auth, data=data)
    response.raise_for_status()
    token_json = response.json()

    ringcentral_token_data["access_token"] = token_json["access_token"]
    ringcentral_token_data["expires_at"] = datetime.now() + timedelta(seconds=token_json["expires_in"] - 60)
    return ringcentral_token_data["access_token"]

# --- Zoho Access Token via Refresh Token ---
def get_zoho_access_token():
    url = "https://accounts.zoho.com/oauth/v2/token"
    data = {
        "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"],
        "client_id": os.environ["ZOHO_CLIENT_ID"],
        "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
        "grant_type": "refresh_token"
    }
    response = requests.post(url, data=data)
    response.raise_for_status()
    return response.json()["access_token"]

# --- Main Handler ---
def message_new_leads_and_update_zoho():
    zoho_token = get_zoho_access_token()
    today = datetime.now().strftime("%Y-%m-%d")

    zoho_headers = {
        "Authorization": f"Zoho-oauthtoken {zoho_token}"
    }
    params = {
        "criteria": f"(Created_Time:equals:{today})"
    }
    zoho_response = requests.get("https://www.zohoapis.com/crm/v2/Leads/search", headers=zoho_headers, params=params)
    leads = zoho_response.json().get("data", [])

    rc_token = get_ringcentral_token()
    rc_headers = {
        "Authorization": f"Bearer {rc_token}",
        "Content-Type": "application/json"
    }
    sender_number = os.environ["RC_FROM_NUMBER"]

    for lead in leads:
        phone = lead.get("Phone")
        name = lead.get("First_Name", "there")
        lead_id = lead.get("id")

        if phone:
            message = (
                f"Hi {name}, this is Steven from Aurora. I saw your interest in our kitchen deals — "
                "can you share more about your project? Timeline, style, etc. I’d love to help."
            )
            sms_payload = {
                "from": {"phoneNumber": sender_number},
                "to": [{"phoneNumber": phone}],
                "text": message
            }
            sms_response = requests.post(
                "https://platform.ringcentral.com/restapi/v1.0/account/~/extension/~/sms",
                headers=rc_headers,
                json=sms_payload
            )

            if sms_response.status_code == 200:
                update_data = {
                    "data": [{
                        "id": lead_id,
                        "Lead_Status": "Attempted to Contact"
                    }]
                }
                requests.put("https://www.zohoapis.com/crm/v2/Leads", headers=zoho_headers, json=update_data)

@app.route("/message_new_leads", methods=["POST"])
def handle_webhook():
    try:
        message_new_leads_and_update_zoho()
        return jsonify({"success": True, "message": "New leads messaged and updated."}), 200
    except Exception as e:
        print("❌ Error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # use PORT env var if set
    app.run(host="0.0.0.0", port=port, debug=True)

app = app

