import os
import re
import requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif len(digits) == 10:
        return f"+1{digits}"
    else:
        return None

def get_zoho_access_token():
    response = requests.post(
        "https://accounts.zoho.com/oauth/v2/token",
        data={
            "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"],
            "client_id": os.environ["ZOHO_CLIENT_ID"],
            "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
            "grant_type": "refresh_token"
        }
    )
    response.raise_for_status()
    return response.json()["access_token"]

def get_ringcentral_token():
    response = requests.post(
        "https://platform.ringcentral.com/restapi/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        auth=(os.environ['RC_CLIENT_ID'], os.environ['RC_CLIENT_SECRET']),
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": os.environ['RC_JWT']}
    )
    response.raise_for_status()
    return response.json()["access_token"]

def message_new_leads_and_update_zoho():
    zoho_token = get_zoho_access_token()
    zoho_headers = {"Authorization": f"Zoho-oauthtoken {zoho_token}"}

    params = {
        "criteria": "(Lead_Status:equals:)",
        "page": 1,
        "per_page": 100
    }
    zoho_response = requests.get("https://www.zohoapis.com/crm/v2/Leads/search", headers=zoho_headers, params=params)
    print("\U0001F50D Zoho response status:", zoho_response.status_code, flush=True)
    print("\U0001F50D Zoho response body:", zoho_response.text, flush=True)

    leads = zoho_response.json().get("data", [])
    print("\ud83d\udce6 Raw Zoho lead data:", leads, flush=True)
    print("\ud83d\udd22 Number of leads returned:", len(leads), flush=True)

    rc_token = get_ringcentral_token()
    rc_headers = {
        "Authorization": f"Bearer {rc_token}",
        "Content-Type": "application/json"
    }

    sender_number = os.environ["RC_FROM_NUMBER"]

    for lead in leads:
        phone_raw = lead.get("Phone")
        name = lead.get("First_Name", "there")
        lead_id = lead.get("id")

        phone = normalize_phone(phone_raw)
        if not phone:
            print(f"❌ Skipping invalid phone number: {phone_raw}", flush=True)
            continue

        message = (
            f"Hello {name},\n\n"
            "I’m Steven Bridge, an online specialist with Aurora.\n\n"
            "I saw your interest in our kitchen listings — I’d love to help you find the perfect match.\n\n"
            "To better assist, can you share a bit about your project? Style, layout, timeline — anything you’re aiming for.\n\n"
            "Here’s our catalog for quick reference: www.auroracirc.com\n\n"
            "Schedule a call: https://crm.zoho.com/bookings/30minutesmeeting?rid=..."
        )

        payload = {
            "from": {"phoneNumber": sender_number},
            "to": [{"phoneNumber": phone}],
            "text": message
        }

        print(f"\U0001f4e4 Sending to: {phone} | Name: {name}", flush=True)
        print("Payload:", payload, flush=True)

        sms_response = requests.post(
            "https://platform.ringcentral.com/restapi/v1.0/account/~/extension/~/sms",
            headers=rc_headers,
            json=payload
        )
        print("\ud83d\udce9 SMS response:", sms_response.status_code, sms_response.text, flush=True)

        if sms_response.status_code == 200:
            update = {
                "data": [{"id": lead_id, "Lead_Status": "Attempted to Contact"}]
            }
            requests.put("https://www.zohoapis.com/crm/v2/Leads", headers=zoho_headers, json=update)

@app.route("/", methods=["GET"])
def home():
    return "✅ SMS Webhook is Live"

@app.route("/message_new_leads", methods=["POST"])
def run():
    try:
        message_new_leads_and_update_zoho()
        return jsonify({"success": True}), 200
    except Exception as e:
        print("❌ Error:", e, flush=True)
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
