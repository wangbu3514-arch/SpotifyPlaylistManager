import os
import schedule, time, threading
from dotenv import load_dotenv
from SpotifyPlaylistManager import SpotifyPlaylistManager
from flask import Flask, request, jsonify
import datetime

load_dotenv()
auth_info = {
    "access_token": os.getenv("ACCESS_TOKEN"),
    "refresh_token": os.getenv("REFRESH_TOKEN"),
    "client_id": os.getenv("CLIENT_ID"),
    "client_secrete": os.getenv("CLIENT_SECRETE"),
    "openai_api_key": os.getenv("OPENAI_API_KEY")
}

manager = SpotifyPlaylistManager(auth_info)

#-----flask app-----#
app = Flask(__name__)
@app.route("/create_playlist", methods=["POST"])
def create_playlist():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Missing 'name' in request body"}), 400
    elif len(data.get("q")) < 5:
        return jsonify({"error": "too short query text"}), 400
    else:
        manager.ai_playlist_make(q_text=data.get("q"))
        return jsonify({"message": "playlist created successfully"}), 200



@app.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "running"}), 200


#------scheduler------#

def monthly_task():
    today = datetime.date.today()
    # 오늘이 1일이면 실행
    if today.day == 1:
        manager.get_playlist_from_chart(period="monthly", limit=5)
        manager.clear_table(table_name="Weekly_Monthly_Record")

def weekly_task():
    manager.get_playlist_from_chart(period="weekly", limit=5)
    manager.clear_table(table_name="Weekly_Monthly_Record")
    manager.delete_inactive_playlists()

def run_schedule():
    #manage playlist
    schedule.every(10).seconds.do(manager.polling_playlist_last_played)
    schedule.every(10).seconds.do(manager.polling_track_playtime, polling_period_ms = 10000)
    schedule.every().monday.at("00:00").do(weekly_task)
    schedule.every().day.at("00:00").do(monthly_task)
    while True:
        schedule.run_pending()
        time.sleep(1)           # prevent overuse CPU

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=run_schedule, daemon=True)
    scheduler_thread.start()
    # Flask 서버 실행
    app.run(host="0.0.0.0", port=5000)
