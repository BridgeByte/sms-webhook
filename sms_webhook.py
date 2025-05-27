import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# 🔐 Auth functions
def get_zoho_access_token():
    return os.environ["ZOHO_ACCESS_TOKEN"]

def get_ringcentral_token():
    url = "https://platform.ringcentral.com/restapi/oauth/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": os.environ["RC_JWT"]
    }
    auth = (os.environ["RC_CLIENT_ID"], os.environ["RC_CLIENT_SECRET"])
    response = requests.post(url, headers=headers, data=data, auth=auth)
    response.raise_for_status()
    return response.json()["access_token"]

# 📲 SMS + Zoho update
@app.route("/message_new_leads", methods=["POST"])
def handle_webhook():
    try:
        data = request.get_json()
        phone = data.get("phone")
        name = data.get("name", "there")
        email = data.get("email")

        # 🛡️ Get tokens
        zoho_token = get_zoho_access_token()
        rc_token = get_ringcentral_token()

        # 🔎 Lookup lead ID by email (or fallback to phone)
        zoho_headers = {"Authorization": f"Zoho-oauthtoken {zoho_token}"}
        lead_id = None
        if email:
            params = {"criteria": f"(Email:equals:{email})"}
        elif phone:
            params = {"criteria": f"(Phone:equals:{phone})"}
        else:
            return jsonify({"success": False, "error": "Missing phone/email"}), 400

        lookup = requests.get("https://www.zohoapis.com/crm/v2/Leads/search", headers=zoho_headers, params=params)
        if lookup.status_code == 200 and lookup.json().get("data"):
            lead_id = lookup.json()["data"][0]["id"]
        else:
            return jsonify({"success": False, "error": "Lead not found in Zoho."}), 404

        # 📤 Send SMS
        rc_headers = {
            "Authorization": f"Bearer {rc_token}",
            "Content-Type": "application/json"
        }
        sender_number = os.environ["RC_FROM_NUMBER"]
        message = (
            f"Hello {name},\n\n"
            "I’m Steven Bridge, an online specialist with Aurora.\n\n"
            "I saw your interest in our kitchen listings — I’d love to help you find the perfect match.\n\n"
            "To better assist, can you share a bit about your project? Style, layout, timeline — anything you’re aiming for.\n\n"
            "Here’s our catalog: www.auroracirc.com\n"
            "Schedule a call: https://crm.zoho.com/bookings/30minutesmeeting?..."
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

        # ✅ Update lead status
        if sms_response.status_code == 200:
            update_data = {
                "data": [{
                    "id": lead_id,
                    "Lead_Status": "Attempted to Contact"
                }]
            }
            requests.put("https://www.zohoapis.com/crm/v2/Leads", headers=zoho_headers, json=update_data)

        return jsonify({"success": True}), 200

    except Exception as e:
        print("❌ Error:", e)
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
