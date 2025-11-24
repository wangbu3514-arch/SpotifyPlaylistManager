import os
import json
import base64
import uuid
import urllib.parse

import requests
from flask import Flask, redirect, request
from dotenv import load_dotenv, set_key

CLIENT_ID = os.getenv("CLIENT_ID"),
CLIENT_SECRETE = os.getenv("CLIENT_SECRETE"),
REDIRECT_URI = "https://wangbu.pythonanywhere.com/callback"

#constitue authorization scope
scopes = [  "user-read-private",
            "user-read-email",
            "playlist-modify-private",
            "user-top-read",
            "user-library-modify",
            "user-read-playback-state"]

def scope_format(scope_list):
    formatted = ""
    for item in scope_list:
        formatted += item
        formatted += " "
    return formatted

SCOPE = scope_format(scopes)

AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'

app = Flask(__name__)

@app.route("/login")
def login():
    state = str(uuid.uuid4())
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "scope": SCOPE,
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    return redirect(url)

@app.route("/callback")
def callback():
    error = request.args.get('error')
    if error:
        return f"Error: {error}"
    code = request.args.get('code')
    state = request.args.get('state')

    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRETE}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'grant_type': 'authorization_code',
        'state': state,
        'code': code,
        'redirect_uri': REDIRECT_URI
    }

    resp = requests.post(TOKEN_URL, data=data, headers=headers)
    resp.raise_for_status()
    token_info = resp.json()
    set_key(dotenv_path=".env", key_to_set="ACCESS_TOKEN", value_to_set=token_info["access_token"])
    set_key(dotenv_path=".env", key_to_set="REFRESH_TOKEN", value_to_set=token_info["refresh_token"])


    return json.dumps(token_info, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    app.run()



