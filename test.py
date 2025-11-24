import requests

data = {"q": "just make playlist that you want, 좀 신나는 분위기로"}
requests.post(url = "http://127.0.0.1:5000/create_playlist", json=data)