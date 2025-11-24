import os
import schedule, time, threading
from dotenv import load_dotenv, set_key
import uuid
import urllib.parse
import base64
import requests

from SpotifyPlaylistManager import SpotifyPlaylistManager
from flask import Flask, request, jsonify, render_template, redirect, url_for
import datetime

#load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRETE = os.getenv("CLIENT_SECRETE")
REDIRECT_URI = "https://wangbu.pythonanywhere.com/callback"

SCOPES = [
    "user-read-private",
    "user-read-email",
    "playlist-modify-private",
    "user-top-read",
    "user-library-modify",
    "user-read-playback-state"
]

def format_scopes(scopes):
    return " ".join(scopes)

SCOPE = format_scopes(SCOPES)

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

app = Flask(__name__)

@app.route("/")
def get_initial_tokens():
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
    error = request.args.get("error")
    if error:
        return f"Error: {error}"

    code = request.args.get("code")
    state = request.args.get("state")

    # Spotify docs: client_id:client_secret base64
    auth_header = base64.b64encode(
        f"{CLIENT_ID}:{CLIENT_SECRETE}".encode()
    ).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    resp = requests.post(TOKEN_URL, data=data, headers=headers)
    resp.raise_for_status()
    token_info = resp.json()

    # ----- .env 업데이트 -----
    # set_key(".env", "ACCESS_TOKEN", token_info["access_token"])
    # set_key(".env", "REFRESH_TOKEN", token_info["refresh_token"])

    os.environ["ACCESS_TOKEN"] = token_info["access_token"]
    os.environ["REFRESH_TOKEN"] = token_info["refresh_token"]

    return render_template("ai.html", message="Spotify authenticated.")

auth_info = {
    "access_token": os.getenv("ACCESS_TOKEN"),
    "refresh_token": os.getenv("REFRESH_TOKEN"),
    "client_id": os.getenv("CLIENT_ID"),
    "client_secrete": os.getenv("CLIENT_SECRETE"),
    "openai_api_key": os.getenv("OPENAI_API_KEY")
}

manager = SpotifyPlaylistManager(auth_info)

#-----flask app-----#


@app.route("/ai", methods=["GET", "POST"])
def ai_page():
    if request.method == "POST":
        prompt = request.form.get("prompt")

        if len(prompt) < 5:
            return render_template("ai.html", message="Prompt is too short.")

        manager.ai_playlist_make(prompt)
        return render_template("ai.html", message="Playlist created successfully!")

    # if method is GET
    return render_template("ai.html")



@app.route("/chart", methods=["GET", "POST"])
def chart():

    if request.method == "POST" :
        #get data using .form when the method is POST.
        period = request.form.get("period")
        limit  = request.form.get("limit", type=int)

        chart_data = manager.get_playlist_from_chart(period, limit)
        manager.generate_playlist_from_chart(period, limit)

        return render_template(
                "chart.html",
                chart=chart_data,
                period=period,
                limit=limit,
                message="Success"
            )

    #if method is GET
    period = request.args.get("period")
    limit = request.args.get("limit", type=int)

    if period is None:
        return render_template("chart.html", chart=None, period=None, limit=None)

    chart_data = manager.get_playlist_from_chart(period, limit)
    return render_template(
        "chart.html",
        chart=chart_data,
        period=period,
        limit=limit
    )

@app.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "running"}), 200


#------scheduler------#

def monthly_task():
    today = datetime.date.today()

    if today.day == 1:       #execute if today is 1st day of the month
        manager.get_playlist_from_chart(period="monthly", limit=5)  #save top5 tracks of the month.
        manager.clear_table(table_name="Weekly_Monthly_Record")     #reset monthly chart

def weekly_task():
    manager.get_playlist_from_chart(period="weekly", limit=5)   #save top5 tracks of the week.
    manager.clear_table(table_name="Weekly_Monthly_Record")     #reset weekly chart
    manager.delete_inactive_playlists()

def run_schedule():
    #record last-played playlist
    schedule.every(10).seconds.do(manager.polling_playlist_last_played)

    #polling which track is playing
    schedule.every(10).seconds.do(manager.polling_track_playtime, polling_period_ms = 10000)

    #do weekly task at every monday start.
    schedule.every().monday.at("00:00").do(weekly_task)

    #do monthly task at every first day of months.
    schedule.every().day.at("00:00").do(monthly_task)

    while True:
        schedule.run_pending()
        time.sleep(1)           # prevent overuse CPU

# if __name__ == "__main__":
#
#     # scheduler_thread = threading.Thread(target=run_schedule, daemon=True)
#     # scheduler_thread.start()
#     app.run(host="0.0.0.0", port=5000)