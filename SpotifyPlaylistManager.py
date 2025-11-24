import base64
import json
from datetime import datetime as dt, timedelta
import sqlite3
from datetime import datetime

import requests
from openai import OpenAI



class SpotifyPlaylistManager:
    def __init__(self, auth_info):
        """
        :param auth_info:
        {
            access_token:
            refresh_token:
            client_id:
            client_secrete:
            openai_api_key:
        }
        """
        # --------------------- auth ---------------------------#
        self.access_token = auth_info["access_token"]
        self.refresh_token = auth_info["refresh_token"]
        self.client_id = auth_info["client_id"]
        self.client_secrete = auth_info["client_secrete"]
        self.openai_api_key = auth_info["openai_api_key"]

        # --------------------- class variable ----------------------#

        self.prev_player_state = None
        self.curr_player_state = None

        #-------------------------DB init--------------------------------#
        conn = sqlite3.connect("music_data.db")
        cursor = conn.cursor()

        # 테이블 생성
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Weekly_Track_Record (
            ID TEXT PRIMARY KEY,
            Track TEXT NOT NULL,
            Artist TEXT NOT NULL,
            Playtime INTEGER DEFAULT 0
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Monthly_Track_Record (
            ID TEXT PRIMARY KEY,
            Track TEXT NOT NULL,
            Artist TEXT NOT NULL,
            Playtime INTEGER DEFAULT 0
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Alltime_Track_Record (
            ID TEXT PRIMARY KEY,
            Track TEXT NOT NULL,
            Artist TEXT NOT NULL,
            Playtime INTEGER DEFAULT 0
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Playlist_Record (
            Playlist_ID TEXT PRIMARY KEY,
            Playlist_name TEXT NOT NULL,
            Last_played TEXT NOT NULL
        );
        """)

        # 변경사항 저장
        conn.commit()

        # 연결 종료
        conn.close()

    # ---------------------- common method ---------------------- #
    def _get_headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def _refresh_token(self):

        print("Refreshing token...")
        endpoint_url = 'https://accounts.spotify.com/api/token'
        body = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        header = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "Basic " + base64.b64encode(f"{self.client_id}:{self.client_secrete}".encode()).decode()
        }
        resp = requests.post(url=endpoint_url, data=body, headers=header)

        if resp.status_code == 200:
            self.access_token = resp.json()["access_token"]
            if resp.json().get("refresh_token"):
                self.refresh_token = resp.json().get("refresh_token")

        else:
            raise Exception(f"refreshing access token has failed. check status{resp.status_code}")

    def _send_alarm(self):
        raise Exception(f"API quota limit exceeds.")

    def _get_user_id(self):
        endpoint = "https://api.spotify.com/v1/me"
        resp = requests.get(endpoint, headers=self._get_headers())
        print(f"{resp.status_code} from _get_user_id")

        if resp.status_code == 401:
            self._refresh_token()
            self._get_user_id()

        elif resp.status_code == 429:
            self._send_alarm()

        return resp.json()["id"]

    # ----------------------playlist polling ---------------------- #

    def _insert_or_update_playlist(self, playlist_id):
        conn = sqlite3.connect("music_data.db")
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO Playlist_Record (Playlist_ID, Last_played)
        VALUES (?, ?)
        ON CONFLICT(Playlist_ID)
        DO UPDATE SET
            Last_played = excluded.Last_played;
        """, (playlist_id, dt.now().isoformat()))

        conn.commit()
        conn.close()

    def _fetch_all_playlists(self):
        conn = sqlite3.connect("music_data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT Playlist_ID, Last_played FROM Playlist_Record;")
        rows = cursor.fetchall()
        conn.close()
        return [{"Playlist_ID": r[0],"Last_played": r[1]} for r in rows]

    def _delete_playlist_from_db(self, playlist_id):
        conn = sqlite3.connect("music_data.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Playlist_Record WHERE Playlist_ID = ?;", (playlist_id,))
        conn.commit()
        conn.close()

    def clear_table(self, table_name):
        conn = sqlite3.connect("music_data.db")
        cursor = conn.cursor()

        cursor.execute(f"DELETE FROM {table_name};")
        conn.commit()

        cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?;", (table_name,))
        conn.commit()

        conn.close()

    def polling_playlist_last_played(self):
        endpoint = "https://api.spotify.com/v1/me/player?market=KR"
        resp = requests.get(endpoint, headers=self._get_headers())

        if resp.status_code == 200:
            data = resp.json()
            context = data.get("context")

            if context and "playlist" in context.get("uri", ""):
                uri = context["uri"]
                playlist_id = uri.split(":")[-1]
                self._insert_or_update_playlist(playlist_id)
                print(f"✅ Updated playlist ({playlist_id}) at {dt.now()}")

        elif resp.status_code == 204:
            return
        elif resp.status_code == 401:
            self._refresh_token()
            self.polling_playlist_last_played()
        elif resp.status_code == 429:
            self._send_alarm()
            self.polling_playlist_last_played()

    # ---------------------- playlist_delete ---------------------- #
    def delete_inactive_playlists(self, threshold_days=7):
        playlists = self._fetch_all_playlists()
        now = dt.now()
        threshold = timedelta(days=threshold_days)

        for record in playlists:
            last_played_time = dt.fromisoformat(record["Last_played"])
            if now - last_played_time > threshold:
                playlist_id = record["Playlist_ID"]
                self._delete_playlist_in_app(f"spotify:playlist:{playlist_id}")
                self._delete_playlist_from_db(playlist_id)
                print(f"🗑️ Deleted inactive playlist {record['Playlist_name']} ({playlist_id})")

    def _delete_playlist_in_app(self, uri):
        playlist_id = uri.split(":")[-1]
        endpoint = f"https://api.spotify.com/v1/playlists/{playlist_id}/followers"
        resp = requests.delete(endpoint, headers=self._get_headers())

        if resp.status_code == 200:
            print(f"✅ Unfollowed playlist {playlist_id}")
        elif resp.status_code == 401:
            print("⚠️ Token expired. Refreshing...")
            self._refresh_token()
            self._delete_playlist_in_app(uri)
        elif resp.status_code == 429:
            self._send_alarm()
            self._delete_playlist_in_app(uri)
        else:
            print(f"❌ Failed to unfollow {playlist_id}. Status code: {resp.status_code}")


    # ---------------------- calculate accumulated playing time of track ---------------------- #

    def _insert_or_update_playtime(self, spotify_id, track, artist, delta_playtime):
        conn = sqlite3.connect("music_data.db")
        cursor = conn.cursor()
        tables = ["Weekly_Track_record", "Monthly_Track_record", "Alltime_Track_record"]
        for table in tables:

            cursor.execute(f"""
            INSERT INTO {table} (ID, Track, Artist, Playtime)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ID)
            DO UPDATE SET
                Playtime = Playtime + excluded.Playtime;
            """, (spotify_id, track, artist, delta_playtime))

        conn.commit()
        conn.close()

    def polling_track_playtime(self, polling_period_ms):
        """

        :param polling_period_ms: period of polling in microsecond
        :return:
        """
        endpoint = "https://api.spotify.com/v1/me/player?market=KR"
        resp = requests.get(endpoint, headers=self._get_headers())

        if resp.status_code in (200, 204):
            # --- Case: 200 OK or 204 No Content ---
            if resp.status_code == 200:
                self.curr_player_state = resp.json()
            else:
                self.curr_player_state = None

            # --- CASE 1: player turned ON ---
            if self.prev_player_state is None and self.curr_player_state is not None:
                progress_ms = self.curr_player_state.get("progress_ms", 0)
                track = self.curr_player_state["item"]["name"]
                artist = self.curr_player_state["item"]["artists"][0]["name"]
                track_id = self.curr_player_state["item"]["id"]

                progress_delta = 0 if progress_ms >= 10_000 else progress_ms
                self._insert_or_update_playtime(track_id, track, artist, progress_delta)
                print(f"[ON] new track {track_id} +{progress_delta}ms")

            # --- CASE 2: player turned OFF ---
            elif self.prev_player_state is not None and self.curr_player_state is None:
                print("[OFF] web_player turned off.")

            # --- CASE 3: same track continues ---
            elif (self.prev_player_state is not None and self.curr_player_state is not None
                  and self.prev_player_state["item"]["id"] == self.curr_player_state["item"]["id"]):
                prev_ms = self.prev_player_state.get("progress_ms", 0)
                curr_ms = self.curr_player_state.get("progress_ms", 0)
                progress_delta = curr_ms - prev_ms

                # skip detection
                if progress_delta > polling_period_ms:
                    progress_delta = polling_period_ms
                elif progress_delta < 0:
                    progress_delta = 0

                track = self.curr_player_state["item"]["name"]
                artist = self.curr_player_state["item"]["artists"][0]["name"]
                track_id = self.curr_player_state["item"]["id"]

                self._insert_or_update_playtime(track_id, track, artist, progress_delta)

                print(f"[SAME] {track_id} +{progress_delta}ms")

            # --- CASE 4: track changed ---
            elif (self.prev_player_state is not None and self.curr_player_state is not None
                  and self.prev_player_state["item"]["id"] != self.curr_player_state["item"]["id"]):
                progress_ms = self.curr_player_state.get("progress_ms", 0)
                track = self.curr_player_state["item"]["name"]
                artist = self.curr_player_state["item"]["artists"][0]["name"]
                track_id = self.curr_player_state["item"]["id"]

                progress_delta = 0 if progress_ms >= 10_000 else progress_ms

                self._insert_or_update_playtime(track_id, track, artist, progress_delta)

                print(f"[CHANGE] new track {track_id} +{progress_delta}ms")

        elif resp.status_code == 401:
            self._refresh_token()
            self.polling_track_playtime(polling_period_ms)

        elif resp.status_code == 429:
            self._send_alarm()

        self.prev_player_state = self.curr_player_state

    # ---------------------------------generate new playlist-----------------#
    def _create_empty_playlist(self, playlist_name, description):
        endpoint = f"https://api.spotify.com/v1/users/{self._get_user_id()}/playlists"
        data = {
            "name": playlist_name,
            "description": description,
            "public": False
        }

        resp = requests.post(url=endpoint, headers=self._get_headers(), json=data)
        print(resp.status_code)
        if resp.status_code == 201:
            print(f"new playlist {playlist_name} was successfully generated.")
            play_list_id = resp.json()["id"]
            return play_list_id
        elif resp.status_code == 401:
            self._refresh_token()
            self._create_empty_playlist(playlist_name, description)
        elif resp.status_code == 429:
            self._send_alarm()
        return None

    def _find_track_uri(self, track_name, artist_name):
        endpoint = "https://api.spotify.com/v1/search"
        parameters = {
            "q": f"track:{track_name} artist:{artist_name}",
            "type": "track",
            "market": "KR",
            "limit": "1",
        }
        resp = requests.get(url=endpoint, headers=self._get_headers(), params=parameters)

        if resp.status_code == 200:
            data = resp.json()
            print(data)
            return data["tracks"]["items"][0]["uri"]

        elif resp.status_code == 401:
            self._refresh_token()
            self._find_track_uri(track_name, artist_name)

        elif resp.status_code == 429:
            self._send_alarm()
        return None

    def _add_track_to_playlist(self, track_list, playlist_id):
        """
        :param track_list: [{"track_name": track, "artist_name": artist}, ... ]
        :param playlist_id: Spotify_id of playlist
        :return:
        """
        endpoint = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        spotify_uris = [
            uri
            for item in track_list
            if (uri := self._find_track_uri(item["track_name"], item["artist_name"]))
            # check track exist in search result
        ]
        # if there's no valid tracks at all
        if not spotify_uris:
            print("❌ No valid tracks found to add.")
            return

        data = {
            "uris": spotify_uris,
            "position": 0
        }
        resp = requests.post(url=endpoint, headers=self._get_headers(), json=data)
        if resp.status_code == 201:
            print(f"✅ Added {len(spotify_uris)} tracks successfully!")
        elif resp.status_code == 401:
            self._refresh_token()
        elif resp.status_code == 429:
            self._send_alarm()

    def _track_valid_check(self, track_name, artist_name):
        """
        search if a track exist in spotify
        :return: Boolean
        """
        endpoint = "https://api.spotify.com/v1/search"
        parameters = {
            "q": f"track:{track_name} artist:{artist_name}",
            "type": "track",
            "market": "KR",
            "limit": "1",
        }
        resp = requests.get(url=endpoint, headers=self._get_headers(), params=parameters)

        if resp.status_code == 200:
            data = resp.json()
            items = data["tracks"]["items"]
            if not items:
                print(f"⚠️ '{track_name}' by '{artist_name}' not found on Spotify.")
                return False
            else:
                print(f"⚠✅ '{track_name}' by '{artist_name}' is available on Spotify.")
                return True
        elif resp.status_code == 401:
            self._refresh_token()
            self._find_track_uri(track_name, artist_name)

        elif resp.status_code == 429:
            self._send_alarm()
        return None

    def ai_playlist_make(self, q_text):
        client = OpenAI(api_key=self.openai_api_key)

        request_template = (
            "Respond strictly in the following JSON format:\n"
            "{\n"
            '  "playlist_title": "<text>",\n'  
            '  "description": "<text>",\n'
            '  "track_list": [\n'
            '    {"track_name": "<name1>", "artist_name": "<artist1>"},\n'
            '    {"track_name": "<name2>", "artist_name": "<artist2>"}\n'
            '    ...\n'
            "  ]\n"
            "}\n\n"
            "Each element in track_list must be a dictionary with the keys 'track_name' and 'artist_name'.\n"
            "Do not include any explanations, comments, or additional text outside this JSON structure."
        )

        response = client.responses.create(
            model="gpt-4.1",
            input=q_text + request_template
        )
        print(response.output_text)
        json_data = json.loads(response.output_text)

        unobtainable_tracks = [
            item for item in json_data.get("track_list") if not self._track_valid_check(item["track_name"], item["artist_name"])
        ]

        while unobtainable_tracks:
            re_request_template = (
                f"The following tracks were unobtainable on Spotify: {unobtainable_tracks}.\n"
                "Please replace each unavailable track with a similar one "
                "Please keep available tracks included in the list."
                "(in mood, genre, and era) that exists on Spotify.\n\n"

                "Respond strictly in the following JSON format:\n"
                "{\n"
                '  "playlist_title": "<text>",\n'  
                '  "description": "<text>",\n'
                '  "track_list": [\n'
                '    {"track_name": "<name1>", "artist_name": "<artist1>"},\n'
                '    {"track_name": "<name2>", "artist_name": "<artist2>"}\n'
                '    ...\n'
                "  ]\n"
                "}\n\n"
                "}\n\n"
                "Each element in track_list must be a dictionary with the keys 'track_name' and 'artist_name'.\n"
                "Do not include any explanations, comments, or additional text outside this JSON structure."
            )

            response = client.responses.create(
                model="gpt-4.1",
                input=re_request_template
            )
            print(response.output_text)
            json_data = json.loads(response.output_text)
            unobtainable_tracks = [
                item for item in json_data.get("track_list") if
                not self._track_valid_check(item["track_name"], item["artist_name"])
            ]

        title = json_data.get("playlist_title")
        description = json_data.get("description")
        track_list = json_data.get("track_list")

        playlist_id = self._create_empty_playlist(title, description)
        self._add_track_to_playlist(track_list, playlist_id)

        print("playlist was successfully generated. please check on spotify")

    def get_playlist_from_chart(self, period, limit):
        """
        :param period: 'weekly', 'monthly', 'all-time'
        :param limit: int
        :return: JSON 호환 리스트: [{"Track": ..., "Artist": ..., "Playtime": ...}, ...]
        """

        table_map = {
            "weekly": "Weekly_Track_Record",
            "monthly": "Monthly_Track_Record",
            "all-time": "Alltime_Track_Record"
        }

        table_name = table_map.get(period.lower())

        conn = sqlite3.connect("music_data.db")
        cursor = conn.cursor()

        query = f"""
            SELECT Track, Artist, Playtime
            FROM {table_name}
            ORDER BY Playtime DESC
            LIMIT ?;
        """
        cursor.execute(query, (limit,))
        results = cursor.fetchall()
        conn.close()

        if not results:
            print(f"⚠️ {table_name} has no data.")
            return []

        # 결과를 JSON 호환 리스트로 변환
        chart_data = [
            {"Track": track, "Artist": artist, "Playtime": playtime}
            for (track, artist, playtime) in results
        ]

        return chart_data

    def generate_playlist_from_chart(self, period, limit):
        """
        :param period: str, 'weekly', 'monthly', 'all-time' 중 하나
               ,limit : int, number of top-n songs.
        :return: create playlist in Spotify app
        """
        table_map = {
            "weekly": "Weekly_Track_Record",
            "monthly": "Monthly_Track_Record",
            "all-time": "Alltime_Track_Record"
        }
        table_name = table_map.get(period.lower())

        conn = sqlite3.connect("music_data.db")
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT Track, Artist 
            FROM {table_name}
            ORDER BY Playtime DESC
            LIMIT {limit};
        """)
        results = cursor.fetchall()
        conn.close()

        if not results:
            print(f"⚠️ {table_name} 테이블에 데이터가 없습니다.")
            return

        track_list = [
            {"track_name": track, "artist_name": artist}
            for track, artist in results
        ]

        today = datetime.now().strftime("%Y-%m-%d")
        playlist_name = f"{period.capitalize()} Chart - {today}"
        description = f"Top tracks from {period} chart generated on {today}"

        playlist_id = self._create_empty_playlist(playlist_name, description)
        if not playlist_id:
            print("❌ 플레이리스트 생성에 실패했습니다.")
            return

        self._add_track_to_playlist(track_list, playlist_id)
        print(f"🎶 '{playlist_name}' Spotify 플레이리스트 생성 완료!")















    


