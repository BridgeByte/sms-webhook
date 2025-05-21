from flask import Flask, request, jsonify
import requests
import os
import time
from base64 import b64encode

app = Flask(__name__)

# RingCentral config
rc_client_id = os.environ.get("RC_CLIENT_ID")
rc_client_secret = os.environ.get("RC_CLIENT_SECRET")
rc_access_token = os.environ.get("RC_ACCESS_TOKEN")
rc_refresh_token = os.environ.get("RC_REFRESH_TOKEN")
platform_url = "https://platform.ringcentral.com"
sender_number = "+12014096774"

# Token cache for RC
rc_token_info = {
    "access_token": rc_access_token,
    "refresh_token": rc_refresh_token,
    "expires_at": time.time() + 3500  # Approx 58 minutes
}

# Zoho config
zoho_client_id = os.environ.get("ZOHO_CLIENT_ID")
zoho_client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
zoho_refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN")
zoho_token = None
zoho_token_expires_at = 0

# Your name in Zoho CRM
your_name = os.environ.get("YOUR_NAME")

def refresh_rc_token():
    print("🔄 Refreshing RingCentral token...")
    auth_header = "Basic " + b64encode(f"{rc_client_id}:{rc_client_secret}".encode()).decode()
    res = requests.post(
        f"{platform_url}/restapi/oauth/token",
        headers={"Authorization": auth_header, "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": rc_token_info["refresh_token"]}
    )
    if res.status_code == 200:
        data = res.json()
        rc_token_info["access_token"] = data["access_token"]
        rc_token_info["refresh_token"] = data["refresh_token"]
        rc_token_info["expires_at"] = time.time() + int(data["expires_in"]) - 60
        return rc_token_info["access_token"]
    else:
        print("❌ Failed to refresh RingCentral token:", res.text)
        raise Exception("RingCentral token refresh failed")

def get_rc_token():
    if time.time() >= rc_token_info["expires_at"]:
        return refresh_rc_token()
    return rc_token_info["access_token"]

def get_zoho_token():
    global zoho_token, zoho_token_expires_at
    if zoho_token and time.time() < zoho_token_expires_at:
        return zoho_token

    res = requests.post(
        "https://accounts.zoho.com/oauth/v2/token",
        data={
            "refresh_token": zoho_refresh_token,
            "client_id": zoho_client_id,
            "client_secret": zoho_client_secret,
            "grant_type": "refresh_token"
        }
    )

    if res.status_code == 200:
        j = res.json()
        zoho_token = j["access_token"]
        zoho_token_expires_at = time.time() + int(j["expires_in"]) - 60
        return zoho_token
    else:
        print("❌ Zoho token refresh failed", res.text)
        raise Exception("Zoho token error")

@app.route('/send-sms', methods=['POST'])
def send_sms():
    data = request.json
    print("📥 Incoming webhook:", data)

    phone = data.get("phone")
    name = data.get("name", "there")
    email = data.get("email")
    owner = data.get("owner")

    if not phone or not email:
        return jsonify({"error": "Missing phone or email"}), 400

    if owner != your_name:
        print("⏭️ Lead not assigned to you.")
        return jsonify({"skipped": "Not your lead"}), 200

    message = f"""Hello {name}, My name is Steven Bridge—an online specialist with Aurora.

I see that you’re interested in our kitchen deals. In order to better assist you:

May I know more about your kitchen project/goals?

https://auroracirc.com/"""

    try:
        rc_token = get_rc_token()
        rc_res = requests.post(
            f"{platform_url}/restapi/v1.0/account/~/extension/~/sms",
            headers={
                "Authorization": f"Bearer {rc_token}",
                "Content-Type": "application/json"
            },
            json={
                "from": {"phoneNumber": sender_number},
                "to": [{"phoneNumber": phone}],
                "text": message
            }
        )
        if rc_res.status_code != 200:
            print("❌ SMS send error:", rc_res.text)
            return jsonify({"error": "SMS failed"}), 403
        print("✅ SMS sent")
    except Exception as e:
        return jsonify({"error": f"RingCentral error: {str(e)}"}), 500

    # Update Zoho CRM lead status
    try:
        zoho_token_val = get_zoho_token()
        search = requests.get(
            f"https://www.zohoapis.com/crm/v2/Leads/search?email={email}",
            headers={"Authorization": f"Zoho-oauthtoken {zoho_token_val}"}
        )
        records = search.json().get("data", [])
        if not records:
            return jsonify({"warning": "Lead not found in Zoho"}), 404

        lead_id = records[0]["id"]
        update = requests.put(
            f"https://www.zohoapis.com/crm/v2/Leads/{lead_id}",
            headers={
                "Authorization": f"Zoho-oauthtoken {zoho_token_val}",
                "Content-Type": "application/json"
            },
            json={"data": [{"Lead_Status": "Attempted to Contact"}]}
        )

        if update.status_code == 200:
            print("✅ Zoho status updated")
            return jsonify({"status": "SMS sent & Zoho updated"}), 200
        else:
            print("⚠️ Zoho update failed:", update.text)
            return jsonify({"warning": "SMS sent but Zoho update failed"}), 207
    except Exception as e:
        return jsonify({"error": f"Zoho error: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
