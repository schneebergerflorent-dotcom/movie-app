from flask import Flask, request, jsonify
from google.cloud import bigquery
import requests
import os
from functools import lru_cache
from elasticsearch import Elasticsearch

app = Flask(__name__)

# ---------------- BIGQUERY CLIENT ----------------
bq = bigquery.Client()

# ---------------- TMDB CONFIG ----------------
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_ACCESS_TOKEN = os.getenv("TMDB_ACCESS_TOKEN")

TMDB_HEADERS = {}
if TMDB_ACCESS_TOKEN:
    TMDB_HEADERS["Authorization"] = f"Bearer {TMDB_ACCESS_TOKEN}"
    

ELASTIC_ENDPOINT = os.getenv("ELASTIC_ENDPOINT")
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")
ELASTIC_INDEX = os.getenv("ELASTIC_INDEX", "movies_autocomplete")

es = None
if ELASTIC_ENDPOINT and ELASTIC_API_KEY:
    es = Elasticsearch(ELASTIC_ENDPOINT, api_key=ELASTIC_API_KEY)


# ===========================================================
# ✅ TMDB helper with caching (robust, no-crash)
# ===========================================================
@lru_cache(maxsize=500)
def fetch_tmdb_details(tmdb_id):
    if tmdb_id is None:
        return {}

    try:
        tmdb_id = int(tmdb_id)
    except (TypeError, ValueError):
        return {}

    if not TMDB_API_KEY and not TMDB_ACCESS_TOKEN:
        return {}

    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
    params = {"append_to_response": "credits"}
    if TMDB_API_KEY:
        params["api_key"] = TMDB_API_KEY

    try:
        r = requests.get(url, headers=TMDB_HEADERS, params=params, timeout=10)
    except requests.RequestException:
        return {}

    if r.status_code != 200:
        return {}

    try:
        data = r.json()
    except ValueError:
        return {}

    poster_url = None
    poster_path = data.get("poster_path")
    if poster_path:
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"

    return {
        "poster_url": poster_url,
        "title": data.get("title"),
        "overview": data.get("overview"),
        "release_date": data.get("release_date"),
        "genres": [g.get("name") for g in data.get("genres", []) if g.get("name")],
        "cast": [
            c.get("name")
            for c in (data.get("credits", {}) or {}).get("cast", [])[:10]
            if c.get("name")
        ],
    }


# ===========================================================
# ✅ HEALTH CHECK
# ===========================================================
@app.route("/health")
def health():
    return jsonify({"status": "ok"})



# ===========================================================
# ✅ RECOMMENDATION (BigQuery ML)
# ===========================================================
@app.route("/recommend", methods=["POST"])
def recommend():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")

    if user_id is None:
        return jsonify({"error": "user_id is required"}), 400

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"error": "user_id must be an integer"}), 400

    sql = f"""
    SELECT
      r.userId,
      r.movieId,
      m.title,
      r.predicted_rating_im_confidence,
      m.tmdbId
    FROM ML.RECOMMEND(
      MODEL `assignment1-489216.movies_dataset.recommender_model`,
      (SELECT {user_id} AS userId)
    ) AS r
    JOIN `assignment1-489216.movies_dataset.movies` AS m
      ON r.movieId = m.movieId
    LIMIT 10
    """

    df = bq.query(sql).to_dataframe()
    results = df.to_dict(orient="records")

    for movie in results:
        tmdb_id = movie.get("tmdbId")
        if tmdb_id:
            movie.update(fetch_tmdb_details(tmdb_id))

    return jsonify(results)


# ===========================================================
# ✅ COLDSTART RECOMMENDATIONS
# ===========================================================
@app.route("/coldstart", methods=["POST"])
def coldstart():
    data = request.get_json(silent=True) or {}
    liked_movies = data.get("liked_movies")

    if not isinstance(liked_movies, list) or not liked_movies:
        return jsonify({"error": "liked_movies must be a non-empty list"}), 400

    try:
        liked_movies = [int(x) for x in liked_movies]
    except (TypeError, ValueError):
        return jsonify({"error": "liked_movies must be a list of integers"}), 400

    sql_similar_users = """
    SELECT userId, COUNT(*) AS overlap
    FROM `assignment1-489216.movies_dataset.ratings`
    WHERE movieId IN UNNEST(@liked_movies)
      AND rating >= 4.0
    GROUP BY userId
    ORDER BY overlap DESC
    LIMIT 20
    """

    job_users = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("liked_movies", "INT64", liked_movies)
        ]
    )

    similar_users_df = bq.query(sql_similar_users, job_config=job_users).to_dataframe()
    if similar_users_df.empty:
        return jsonify([])

    similar_users = similar_users_df["userId"].tolist()

    sql_reco = """
    SELECT movieId, AVG(rating) AS score
    FROM `assignment1-489216.movies_dataset.ratings`
    WHERE userId IN UNNEST(@similar_users)
      AND rating >= 4.0
    GROUP BY movieId
    ORDER BY score DESC
    LIMIT 50
    """

    job_reco = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("similar_users", "INT64", similar_users)
        ]
    )

    reco_df = bq.query(sql_reco, job_config=job_reco).to_dataframe()
    if reco_df.empty:
        return jsonify([])

    reco_df = reco_df[~reco_df["movieId"].isin(liked_movies)]
    if reco_df.empty:
        return jsonify([])

    sql_movies = """
    SELECT movieId, title, tmdbId
    FROM `assignment1-489216.movies_dataset.movies`
    WHERE movieId IN UNNEST(@movie_ids)
    """

    job_movies = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("movie_ids", "INT64", reco_df["movieId"].tolist())
        ]
    )

    movies_df = bq.query(sql_movies, job_config=job_movies).to_dataframe()
    final_df = reco_df.merge(movies_df, on="movieId", how="inner")
    results = final_df.to_dict(orient="records")

    for movie in results:
        tmdb_id = movie.get("tmdbId")
        if tmdb_id:
            movie.update(fetch_tmdb_details(tmdb_id))

    return jsonify(results)


# ===========================================================
# ✅ TMDB DETAILS ENDPOINTS
# ===========================================================
@app.route("/movie/<int:tmdb_id>", methods=["GET"])
def tmdb_details_get(tmdb_id):
    return jsonify(fetch_tmdb_details(tmdb_id))


@app.route("/movie-details", methods=["POST"])
def tmdb_details_post():
    data = request.get_json(silent=True) or {}
    tmdb_id = data.get("tmdb_id")
    if tmdb_id is None:
        return jsonify({"error": "missing tmdb_id"}), 400
    return jsonify(fetch_tmdb_details(tmdb_id))

@app.route("/autocomplete", methods=["GET"])
def autocomplete_titles():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])

    if es is None:
        return jsonify([])

    body = {
        "size": 10,  # ✅ tu voulais 10
        "_source": ["title", "movieId", "tmdbId"],
        "query": {
            "match": {
                "title": {
                    "query": q
                }
            }
        }
    }

    resp = es.search(index=ELASTIC_INDEX, body=body)
    hits = resp.get("hits", {}).get("hits", [])

    out = []
    for h in hits:
        src = h.get("_source", {})
        if src.get("title"):
            out.append({
                "title": src.get("title"),
                "movieId": src.get("movieId"),
                "tmdbId": src.get("tmdbId")
            })

    return jsonify(out)


# ===========================================================
# ✅ RUN SERVER (local only)
# ===========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
