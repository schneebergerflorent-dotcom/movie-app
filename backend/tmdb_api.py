import requests
import os

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_ACCESS_TOKEN = os.getenv("TMDB_ACCESS_TOKEN")

def get_movie_details(movie_id):
    # ---- Validate movie_id ----
    if movie_id is None:
        return _empty_details()

    try:
        movie_id = int(movie_id)
    except (TypeError, ValueError):
        return _empty_details()

    url = f"https://api.themoviedb.org/3/movie/{movie_id}"

    headers = {}
    # Bearer token is enough for v4 auth; keep it if you have it
    if TMDB_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_ACCESS_TOKEN}"

    params = {"append_to_response": "credits"}
    # If you also use an API key, include it (some setups require it)
    if TMDB_API_KEY:
        params["api_key"] = TMDB_API_KEY

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
    except requests.RequestException:
        # Network error, timeout, DNS, etc.
        return _empty_details()

    # ---- Handle non-200 status codes ----
    if response.status_code != 200:
        # Optional debug (uncomment if needed):
        # print("TMDB error:", response.status_code, response.text[:200])
        return _empty_details()

    # ---- Safe JSON parsing ----
    try:
        data = response.json()
    except ValueError:
        # Response wasn't JSON (or was empty)
        # Optional debug:
        # print("Non-JSON TMDB response:", response.text[:200])
        return _empty_details()

    poster_path = data.get("poster_path")
    return {
        "title": data.get("title"),
        "overview": data.get("overview"),
        "poster": f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
        "genres": [g.get("name") for g in data.get("genres", []) if g.get("name")],
        "release_date": data.get("release_date"),
        "cast": [
            c.get("name")
            for c in (data.get("credits", {}) or {}).get("cast", [])[:10]
            if c.get("name")
        ],
    }

def _empty_details():
    return {
        "title": None,
        "overview": None,
        "poster": None,
        "genres": [],
        "release_date": None,
        "cast": [],
    }
