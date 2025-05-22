from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timedelta
import traceback

app = Flask(__name__)

@app.route("/", methods=["GET"])
def health_check():
    return "✅ Flask is running"

# --- RingCentral Token Cache ---
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

def message_new_leads_and_update_zoho():
    zoho_token = get_zoho_access_token()
    zoho_headers = {
        "Authorization": f"Zoho-oauthtoken {zoho_token}"
    }

    today = datetime.now().strftime("%Y-%m-%d")
    params = {
        "criteria": f"(Created_Time:equals:{today}) and (Lead_Status:is_empty:true)"
    }

    zoho_response = requests.get("https://www.zohoapis.com/crm/v2/Leads/search", headers=zoho_headers, params=params)
    leads = zoho_response.json().get("data", [])

    print("📦 Raw Zoho lead data:", leads, flush=True)
    print("🔢 Number of leads returned:", len(leads), flush=True)

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
                f"Hello {name},\n\n"
                "I’m Steven Bridge, an online specialist with Aurora.\n\n"
                "I saw your interest in our kitchen listings — I’d love to help you find the perfect match.\n\n"
                "To better assist, can you share a bit about your project? Style, layout, timeline — anything you’re aiming for.\n\n"
                "Here’s our catalog for quick reference: www.auroracirc.com\n\n"
                "Schedule a call: https://crm.zoho.com/bookings/30minutesmeeting?rid=3a8797334b8eeb0c2e8307050c50ed050800079fc6b8ec749e969fa4a35b69c3c92eea5b30c8b3bd6b03ff14a82a87bfgid9bbeef68668955f8615e7755cd1286847d3ce2e658291f6b9afc77df15a363d5"
            )
            sms_payload = {
                "from": {"phoneNumber": sender_number},
                "to": [{"phoneNumber": phone}],
                "text": message
            }

            print("📤 Attempting to send SMS to:", phone, flush=True)
            print("📨 Message text:", message, flush=True)
            print("📄 Payload:", sms_payload, flush=True)

            sms_response = requests.post(
                "https://platform.ringcentral.com/restapi/v1.0/account/~/extension/~/sms",
                headers=rc_headers,
                json=sms_payload
            )

            print("📬 RingCentral SMS API response:", sms_response.status_code, sms_response.text, flush=True)

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
        print("❌ Error:", e, flush=True)
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

app = app
