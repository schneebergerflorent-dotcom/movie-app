import requests
import os

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_ACCESS_TOKEN = os.getenv("TMDB_ACCESS_TOKEN")

def get_movie_details(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    headers = {"Authorization": f"Bearer {TMDB_ACCESS_TOKEN}"}
    params = {"api_key": TMDB_API_KEY, "append_to_response": "credits"}

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    return {
        "title": data.get("title"),
        "overview": data.get("overview"),
        "poster": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else None,
        "genres": [g["name"] for g in data.get("genres", [])],
        "release_date": data.get("release_date"),
        "cast": [c["name"] for c in data.get("credits", {}).get("cast", [])[:10]]
    }

