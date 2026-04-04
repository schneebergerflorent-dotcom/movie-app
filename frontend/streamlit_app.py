import os
import re
import requests
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from streamlit_searchbox import st_searchbox

# ==========================================================
# PAGE CONFIG
# ==========================================================
st.set_page_config(page_title="Movie Explorer", page_icon="🎬", layout="wide")

# ==========================================================
# MINI CSS — keep your UI unchanged
# ==========================================================
st.markdown("""""", unsafe_allow_html=True)

# ==========================================================
# TITLE NORMALIZER (display only)
# Converts 'Movie, The (1999)' -> 'The Movie (1999)'
# ==========================================================
def display_title(title: str) -> str:
    """Affichage plus naturel : 'Movie, The (1999)' -> 'The Movie (1999)'.
    DISPLAY ONLY: ne change pas les données, juste l'affichage.
    """
    if not title:
        return title

    # Conserver le suffixe (YYYY) à la fin si présent
    m_year = re.match(r"^(.*?)(\s*\(\d{4}\))$", title)
    base, year = (m_year.group(1), m_year.group(2)) if m_year else (title, "")

    # Convertir 'X, The' / 'X, A' / 'X, An' en 'The X' / 'A X' / 'An X'
    m = re.match(r"^(.*?),\s*(The|A|An)\b(.*)$", base, flags=re.IGNORECASE)
    if not m:
        return title

    main = m.group(1).strip()
    art = m.group(2).strip()
    rest = (m.group(3) or "").strip()
    rest = f" {rest}" if rest else ""

    return f"{art} {main}{rest}{year}"

# ==========================================================
# CONSTANTS / CLIENTS
# ==========================================================
GRID_COLS = 8
GRID_ROWS = 5
SHOW_COUNT = GRID_COLS * GRID_ROWS  # 40 per page

client = bigquery.Client()
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")

# ==========================================================
# AUTOCOMPLETE (Elastic/Backend) — suggestions only (Mode A)
# ==========================================================
@st.cache_data(show_spinner=False, ttl=2)
def es_autocomplete(q: str):
    q = (q or "").strip()
    if len(q) < 1:
        return []
    try:
        r = requests.get(f"{BACKEND_URL}/autocomplete", params={"q": q}, timeout=6)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def searchbox_provider(q: str):
    items = es_autocomplete(q)
    ac_map = {}
    for it in items:
        raw = (it.get("title_raw") or it.get("title") or "").strip()
        if raw:
            disp = display_title(raw)
            ac_map[disp] = raw
    st.session_state["ac_map"] = ac_map
    return list(ac_map.keys())

# ==========================================================
# SESSION STATE DEFAULTS
# ==========================================================
def _init_state():
    defaults = {
        "ac_map": {},
        "selected_movie_id": None,
        "selected_title": None,
        "last_results": None,
        "recos": None,
        "liked_movies": [],
        "liked_titles": [],
        "liked_tmdb_ids": [],
        "search_results": None,
        "selected_tmdb": None,
        "selected_movieid": None,
        "results_offset": 0,
        "show_results": True,
        "show_liked": True,
        # cache global recos in session
        "global_recos": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()

# ==========================================================
# BIGQUERY HELPERS
# ==========================================================
@st.cache_data(show_spinner=False, ttl=600)
def get_all_movies():
    """Fetch all movies for empty search + no filters (cached)."""
    sql = """
    SELECT movieId, tmdbId, title
    FROM `assignment1-489216.movies_dataset.movies`
    ORDER BY title
    """
    return client.query(sql).to_dataframe()


@st.cache_data(show_spinner=False, ttl=600)
def get_global_recommendations(limit: int = 10, min_votes: int = 50):
    """Generic recommendations: high average rating with many ratings.

    We use a robust score: AVG(rating) * LN(COUNT(rating)+1).
    This favors both high score and many critics.
    """
    sql = """
    SELECT
      m.movieId,
      m.tmdbId,
      m.title,
      AVG(r.rating) AS avg_rating,
      COUNT(r.rating) AS rating_count,
      (AVG(r.rating) * LN(COUNT(r.rating) + 1)) AS score
    FROM `assignment1-489216.movies_dataset.movies` m
    JOIN `assignment1-489216.movies_dataset.ratings` r
      ON m.movieId = r.movieId
    GROUP BY m.movieId, m.tmdbId, m.title
    HAVING COUNT(r.rating) >= @min_votes
    ORDER BY score DESC, rating_count DESC
    LIMIT @limit
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("limit", "INT64", int(limit)),
            bigquery.ScalarQueryParameter("min_votes", "INT64", int(min_votes)),
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def search_movies_by_release_year(min_year):
    sql = """
    SELECT movieId, title, release_year, tmdbId
    FROM `assignment1-489216.movies_dataset.movies`
    WHERE release_year IS NOT NULL AND release_year >= @min_year
    ORDER BY ABS(CAST(release_year AS INT64) - @min_year) ASC, release_year DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("min_year", "INT64", int(min_year))]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def search_movies_by_min_rating(min_rating):
    sql = """
    SELECT m.movieId, m.title, m.tmdbId,
           AVG(r.rating) AS avg_rating,
           COUNT(r.rating) AS rating_count
    FROM `assignment1-489216.movies_dataset.movies` AS m
    JOIN `assignment1-489216.movies_dataset.ratings` AS r
      ON m.movieId = r.movieId
    GROUP BY m.movieId, m.title, m.tmdbId
    HAVING AVG(r.rating) >= @min_rating
    ORDER BY (AVG(r.rating) * LN(COUNT(r.rating) + 1)) DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("min_rating", "FLOAT64", float(min_rating))]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def search_movies_by_genre(genre):
    sql = """
    SELECT movieId, tmdbId, title, genres
    FROM `assignment1-489216.movies_dataset.movies`
    WHERE LOWER(genres) LIKE LOWER(CONCAT('%', @genre, '%'))
    ORDER BY title
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("genre", "STRING", genre)]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def get_all_genres():
    # genres are pipe-separated: Action|Comedy|...
    sql = """
    WITH exploded AS (
      SELECT TRIM(g) AS genre
      FROM `assignment1-489216.movies_dataset.movies`,
      UNNEST(SPLIT(genres, '|')) AS g
    )
    SELECT DISTINCT genre
    FROM exploded
    WHERE genre IS NOT NULL AND genre != ''
    ORDER BY genre
    """
    return client.query(sql).to_dataframe()


def get_all_languages():
    sql = """
    SELECT DISTINCT language
    FROM `assignment1-489216.movies_dataset.movies`
    WHERE language IS NOT NULL
    ORDER BY language
    """
    return client.query(sql).to_dataframe()


def search_movies_by_language(language):
    sql = """
    SELECT movieId, tmdbId, title, language
    FROM `assignment1-489216.movies_dataset.movies`
    WHERE language = @language
    ORDER BY title
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("language", "STRING", language)]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def search_titles_startswith(prefix):
    sql = """
    SELECT movieId, tmdbId, title
    FROM `assignment1-489216.movies_dataset.movies`
    WHERE LOWER(title) LIKE LOWER(CONCAT(@prefix, '%'))
    ORDER BY title
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("prefix", "STRING", prefix)]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def search_titles_contains(prefix):
    sql = """
    SELECT movieId, tmdbId, title
    FROM `assignment1-489216.movies_dataset.movies`
    WHERE LOWER(title) LIKE LOWER(CONCAT('%', @prefix, '%'))
    ORDER BY title
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("prefix", "STRING", prefix)]
    )
    return client.query(sql, job_config=job_config).to_dataframe()

# ==========================================================
# BACKEND CALLS
# ==========================================================
def get_coldstart_recommendations(liked_movies):
    try:
        r = requests.post(f"{BACKEND_URL}/coldstart", json={"liked_movies": liked_movies}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error("Backend error while fetching /coldstart.")
        st.write(e)
        return []

# ==========================================================
# TMDB DETAILS (via BACKEND) + CACHE
# ==========================================================
@st.cache_data(show_spinner=False)
def cached_get_movie_details(tmdb_id):
    if tmdb_id is None:
        return {}
    try:
        tmdb_id = int(tmdb_id)
    except (TypeError, ValueError):
        return {}

    try:
        r = requests.get(f"{BACKEND_URL}/movie/{tmdb_id}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

# ==========================================================
# HELPERS (selection / likes)
# ==========================================================
def select_movie(tmdb_id, movie_id, title):
    st.session_state["selected_tmdb"] = tmdb_id
    st.session_state["selected_movieid"] = movie_id
    st.session_state["selected_title"] = title


def add_like(movie_id, tmdb_id, title):
    if movie_id is None or tmdb_id is None:
        return
    if movie_id not in st.session_state["liked_movies"]:
        st.session_state["liked_movies"].append(movie_id)
        st.session_state["liked_tmdb_ids"].append(tmdb_id)
        st.session_state["liked_titles"].append(title)


def remove_like(movie_id):
    if movie_id in st.session_state["liked_movies"]:
        idx = st.session_state["liked_movies"].index(movie_id)
        st.session_state["liked_movies"].pop(idx)
        st.session_state["liked_tmdb_ids"].pop(idx)
        st.session_state["liked_titles"].pop(idx)

# ==========================================================
# SEARCH (startswith first + filters intersection)
# ==========================================================
def search_movies_by_filters(query=None, language=None, genre=None, min_rating=None, min_year=None):
    query = (query or "").strip()

    # If user clicks Search with no title and no filters => show all movies
    if (not query) and (language is None) and (genre is None) and (min_rating is None) and (min_year is None):
        return get_all_movies()

    if query:
        df_start = search_titles_startswith(query)
        df_contain = search_titles_contains(query)
        df_contain = df_contain[~df_contain["movieId"].isin(df_start["movieId"])]
        df_base = pd.concat([df_start, df_contain], ignore_index=True)
    else:
        df_base = None

    def intersect(df1, df2):
        if df1 is None:
            return df2
        if df2 is None:
            return df1
        if df1.empty or df2.empty:
            return pd.DataFrame(columns=["movieId", "title", "tmdbId"])
        # keep left columns stable
        return df1.merge(df2[["movieId"]].drop_duplicates(), on="movieId", how="inner")

    if language:
        df_base = intersect(df_base, search_movies_by_language(language))
    if genre:
        df_base = intersect(df_base, search_movies_by_genre(genre))
    if min_rating is not None:
        df_base = intersect(df_base, search_movies_by_min_rating(min_rating))
    if min_year is not None:
        df_base = intersect(df_base, search_movies_by_release_year(min_year))

    if df_base is None or df_base.empty:
        return pd.DataFrame(columns=["movieId", "title", "tmdbId"])

    keep = [c for c in ["movieId", "title", "tmdbId"] if c in df_base.columns]
    return df_base[keep].drop_duplicates()

# ==========================================================
# UI — Header
# ==========================================================
st.title("🎬 Movie Explorer")
st.markdown("### Explore movies, like your favorites, and get personalized recommendations.")

# ==========================================================
# SEARCH BAR + FILTERS
# ==========================================================
st.markdown("## 🔍 Search")

chosen = st_searchbox(
    search_function=searchbox_provider,
    placeholder="Search (suggestions only)...",
    key="movie_searchbox",
    clear_on_submit=False,
)

# If a suggestion is selected, copy raw title into the real title filter (Mode A)
if chosen:
    raw = st.session_state.get("ac_map", {}).get(chosen)
    if raw:
        st.session_state["search_query"] = raw

query = st.text_input("Title contains (optional):", key="search_query")

# LANGUAGE NAMES (kept)
LANGUAGE_NAMES = {
    "aa": "Afar", "ab": "Abkhazian", "ae": "Avestan", "af": "Afrikaans", "ak": "Akan",
    "am": "Amharic", "an": "Aragonese", "ar": "Arabic", "as": "Assamese", "av": "Avaric",
    "ay": "Aymara", "az": "Azerbaijani", "ba": "Bashkir", "be": "Belarusian", "bg": "Bulgarian",
    "bh": "Bihari", "bi": "Bislama", "bm": "Bambara", "bn": "Bengali", "bo": "Tibetan",
    "br": "Breton", "bs": "Bosnian", "ca": "Catalan", "ce": "Chechen", "ch": "Chamorro",
    "co": "Corsican", "cr": "Cree", "cs": "Czech", "cu": "Church Slavic", "cv": "Chuvash",
    "cy": "Welsh", "da": "Danish", "de": "German", "dv": "Divehi", "dz": "Dzongkha",
    "ee": "Ewe", "el": "Greek", "en": "English", "eo": "Esperanto", "es": "Spanish",
    "et": "Estonian", "eu": "Basque", "fa": "Persian", "ff": "Fulah", "fi": "Finnish",
    "fj": "Fijian", "fo": "Faroese", "fr": "French", "fy": "Western Frisian", "ga": "Irish",
    "gd": "Scottish Gaelic", "gl": "Galician", "gn": "Guarani", "gu": "Gujarati", "gv": "Manx",
    "ha": "Hausa", "he": "Hebrew", "hi": "Hindi", "ho": "Hiri Motu", "hr": "Croatian",
    "ht": "Haitian", "hu": "Hungarian", "hy": "Armenian", "hz": "Herero", "ia": "Interlingua",
    "id": "Indonesian", "ie": "Interlingue", "ig": "Igbo", "ii": "Sichuan Yi", "ik": "Inupiaq",
    "io": "Ido", "is": "Icelandic", "it": "Italian", "iu": "Inuktitut", "ja": "Japanese",
    "jv": "Javanese", "ka": "Georgian", "kg": "Kongo", "ki": "Kikuyu", "kj": "Kuanyama",
    "kk": "Kazakh", "kl": "Kalaallisut", "km": "Khmer", "kn": "Kannada", "ko": "Korean",
    "kr": "Kanuri", "ks": "Kashmiri", "ku": "Kurdish", "kv": "Komi", "kw": "Cornish",
    "ky": "Kyrgyz", "la": "Latin", "lb": "Luxembourgish", "lg": "Ganda", "li": "Limburgish",
    "ln": "Lingala", "lo": "Lao", "lt": "Lithuanian", "lu": "Luba-Katanga", "lv": "Latvian",
    "mg": "Malagasy", "mh": "Marshallese", "mi": "Maori", "mk": "Macedonian", "ml": "Malayalam",
    "mn": "Mongolian", "mr": "Marathi", "ms": "Malay", "mt": "Maltese", "my": "Burmese",
    "na": "Nauru", "nb": "Norwegian Bokmål", "nd": "North Ndebele", "ne": "Nepali",
    "ng": "Ndonga", "nl": "Dutch", "nn": "Norwegian Nynorsk", "no": "Norwegian",
    "nr": "South Ndebele", "nv": "Navajo", "ny": "Chichewa", "oc": "Occitan", "oj": "Ojibwa",
    "om": "Oromo", "or": "Oriya", "os": "Ossetian", "pa": "Punjabi", "pi": "Pali",
    "pl": "Polish", "ps": "Pashto", "pt": "Portuguese", "qu": "Quechua", "rm": "Romansh",
    "rn": "Rundi", "ro": "Romanian", "ru": "Russian", "rw": "Kinyarwanda", "sa": "Sanskrit",
    "sc": "Sardinian", "sd": "Sindhi", "se": "Northern Sami", "sg": "Sango", "si": "Sinhala",
    "sk": "Slovak", "sl": "Slovenian", "sm": "Samoan", "sn": "Shona", "so": "Somali",
    "sq": "Albanian", "sr": "Serbian", "ss": "Swati", "st": "Southern Sotho", "su": "Sundanese",
    "sv": "Swedish", "sw": "Swahili", "ta": "Tamil", "te": "Telugu", "tg": "Tajik",
    "th": "Thai", "ti": "Tigrinya", "tk": "Turkmen", "tl": "Tagalog", "tn": "Tswana",
    "to": "Tongan", "tr": "Turkish", "ts": "Tsonga", "tt": "Tatar", "tw": "Twi",
    "ty": "Tahitian", "ug": "Uyghur", "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek",
    "ve": "Venda", "vi": "Vietnamese", "vo": "Volapük", "wa": "Walloon", "wo": "Wolof",
    "xh": "Xhosa", "yi": "Yiddish", "yo": "Yoruba", "za": "Zhuang", "zh": "Chinese",
    "zu": "Zulu"
}

with st.expander("Advanced filters"):
    use_language = st.checkbox("Filter by language", key="f_lang")
    use_genre = st.checkbox("Filter by genre", key="f_genre")
    use_rating = st.checkbox("Filter by minimum rating", key="f_rating")
    use_year = st.checkbox("Filter by release year", key="f_year")

    language_choice = None
    genre_choice = None
    min_rating = None
    min_year = None

    if use_language:
        langs_df = get_all_languages()
        languages = langs_df["language"].tolist()
        # keep your original "code: name" style if possible
        language_labels = [f"{code}: {LANGUAGE_NAMES.get(code, 'Unknown')}" for code in languages]
        selected_label = st.selectbox("Select language:", ["-- select --"] + language_labels, key="lang_select")
        if selected_label != "-- select --":
            language_choice = selected_label.split(":")[0].strip()

    if use_genre:
        genres_df = get_all_genres()
        genres = genres_df["genre"].tolist()
        genre_choice = st.selectbox("Select genre:", ["-- select --"] + genres, key="genre_select")
        if genre_choice == "-- select --":
            genre_choice = None

    if use_rating:
        min_rating = st.slider("Minimum rating:", 0.0, 5.0, 4.0, 0.1, key="min_rating")

    if use_year:
        min_year = st.number_input("Released after year:", 1900, 2026, 2000, key="min_year")

if st.button("Search movies", key="btn_search"):
    df = search_movies_by_filters(
        query=query,
        language=language_choice,
        genre=genre_choice,
        min_rating=min_rating,
        min_year=min_year,
    )
    st.session_state["search_results"] = df.to_dict(orient="records") if not df.empty else None
    st.session_state["selected_tmdb"] = None
    st.session_state["selected_movieid"] = None
    st.session_state["results_offset"] = 0
    st.session_state["show_results"] = True

# ==========================================================
# MOVIE DETAILS
# ==========================================================
tmdb_id = st.session_state.get("selected_tmdb")
if tmdb_id:
    st.markdown("## 🎬 Movie Details")
    details = cached_get_movie_details(tmdb_id)

    col1, col2 = st.columns([1, 4])
    with col1:
        poster = details.get("poster") or details.get("poster_url")
        if poster:
            st.image(poster, width=220)

    with col2:
        title = details.get("title", st.session_state.get("selected_title", "Untitled"))
        st.subheader(display_title(title))
        st.write(f"**Release date:** {details.get('release_date', 'Unknown')}")
        st.write(f"**Genres:** {', '.join(details.get('genres', []))}")
        st.write("**Overview:**")
        st.write(details.get("overview", "No overview available."))

        movie_id = st.session_state.get("selected_movieid")
        if movie_id:
            if movie_id not in st.session_state["liked_movies"]:
                if st.button("♥ Like", key=f"detail_like_{tmdb_id}"):
                    add_like(movie_id, tmdb_id, title)
                    st.rerun()
            else:
                if st.button("💔 Unlike", key=f"detail_unlike_{tmdb_id}"):
                    remove_like(movie_id)
                    st.rerun()

# ==========================================================
# RESULTS GRID
# ==========================================================
results = st.session_state.get("search_results")
result_count = len(results) if results else 0

toggle_label = (
    f"🙈 Hide results ({result_count})" if st.session_state["show_results"] else f"👀 Show results ({result_count})"
)
if st.button(toggle_label, key="toggle_results", disabled=(result_count == 0)):
    st.session_state["show_results"] = not st.session_state["show_results"]
    st.rerun()

if st.session_state["show_results"]:
    st.markdown("## 📚 Results")
    if not results:
        st.info("Search for something to get results.")
    else:
        offset = st.session_state["results_offset"]
        end = offset + SHOW_COUNT
        page_results = results[offset:end]

        cols = st.columns(GRID_COLS)
        for i, movie in enumerate(page_results):
            tmdb_id = movie.get("tmdbId")
            movie_id = movie.get("movieId")
            title = movie.get("title", "Untitled")

            with cols[i % GRID_COLS]:
                if not tmdb_id:
                    st.caption(display_title(title))
                    continue

                d = cached_get_movie_details(tmdb_id)
                poster = d.get("poster") or d.get("poster_url")

                b1, b2 = st.columns(2, gap="small")
                with b1:
                    st.button(
                        "▶",
                        key=f"res_open_{tmdb_id}",
                        help=f"Open details: {display_title(title)}",
                        on_click=select_movie,
                        args=(tmdb_id, movie_id, title),
                        use_container_width=True,
                    )

                with b2:
                    if st.button(
                        "♥",
                        key=f"res_like_{tmdb_id}",
                        help=f"Like: {display_title(title)}",
                        use_container_width=True,
                    ):
                        add_like(movie_id, tmdb_id, title)

                if poster:
                    st.image(poster, use_container_width=True)
                st.caption(display_title(title))

        col_prev, col_next = st.columns([1, 1])
        with col_prev:
            if offset > 0 and st.button("⬅️ Previous", key="results_prev"):
                st.session_state["results_offset"] = max(0, offset - SHOW_COUNT)
                st.rerun()

        with col_next:
            if end < len(results) and st.button("Next ➡️", key="results_next"):
                st.session_state["results_offset"] = offset + SHOW_COUNT
                st.rerun()

# ==========================================================
# LIKED MOVIES
# ==========================================================
liked_count = len(st.session_state["liked_movies"])

toggle_liked_label = (
    f"🙈 Hide liked movies ({liked_count})" if st.session_state["show_liked"] else f"👀 Show liked movies ({liked_count})"
)
if st.button(toggle_liked_label, key="toggle_liked", disabled=(liked_count == 0)):
    st.session_state["show_liked"] = not st.session_state["show_liked"]
    st.rerun()

if st.session_state["show_liked"]:
    st.markdown("## ❤️ Your Liked Movies")

    liked_movie_ids = st.session_state["liked_movies"]
    liked_tmdb_ids = st.session_state["liked_tmdb_ids"]
    liked_titles = st.session_state["liked_titles"]

    if liked_movie_ids:
        cols = st.columns(GRID_COLS)
        for i, (tmdb, title, movie_id) in enumerate(zip(liked_tmdb_ids, liked_titles, liked_movie_ids)):
            with cols[i % GRID_COLS]:
                d = cached_get_movie_details(tmdb)
                poster = d.get("poster") or d.get("poster_url")

                b1, b2 = st.columns(2, gap="small")
                with b1:
                    st.button(
                        "▶",
                        key=f"liked_open_{tmdb}",
                        help=f"Open details: {display_title(title)}",
                        on_click=select_movie,
                        args=(tmdb, movie_id, title),
                        use_container_width=True,
                    )

                with b2:
                    if st.button(
                        "🗑",
                        key=f"liked_remove_{tmdb}",
                        help=f"Remove: {display_title(title)}",
                        use_container_width=True,
                    ):
                        remove_like(movie_id)
                        st.rerun()

                if poster:
                    st.image(poster, use_container_width=True)
                st.caption(display_title(title))
    else:
        st.info("You haven't liked any movies yet.")

# ==========================================================
# RECOMMENDATIONS
# ==========================================================
st.markdown("## 🔮 Personalized Recommendations")

liked_count = len(st.session_state["liked_movies"])

# Case 1: No likes => show generic top picks
if liked_count == 0:
    st.caption("No liked movies yet — here are some popular top-rated picks to get you started.")

    # Fetch once (cached) and store in session_state to avoid flicker
    if st.session_state.get("global_recos") is None:
        df_top = get_global_recommendations(limit=24, min_votes=50)
        st.session_state["global_recos"] = df_top.to_dict(orient="records") if not df_top.empty else []

    global_recos = st.session_state.get("global_recos") or []
    if not global_recos:
        st.info("No global recommendations available right now.")
    else:
        cols = st.columns(GRID_COLS)  # 8 columns
        for i, movie in enumerate(global_recos[:24]):  # display 24 (3 rows of 8)
            tm = movie.get("tmdbId")
            mid = movie.get("movieId")
            raw_title = movie.get("title", "Untitled")
            title = display_title(raw_title)

            with cols[i % GRID_COLS]:
                if tm:
                    d = cached_get_movie_details(tm)
                    poster = d.get("poster") or d.get("poster_url")

                    st.button(
                        "▶",
                        key=f"global_open_{tm}_{i}",  # unique key
                        help=f"Open details: {title}",
                        on_click=select_movie,
                        args=(tm, mid, raw_title),
                        use_container_width=True,
                    )

                    if poster:
                        st.image(poster, use_container_width=True)

                st.caption(title)

    st.info("Like a few movies (♥) to unlock personalized recommendations.")

else:
    # Case 2: Personalized recos from backend
    get_recos_clicked = st.button(
        "Get Recommendations",
        key="get_recos",
        disabled=False,
        help=None,
    )

    if get_recos_clicked:
        st.session_state["recos"] = get_coldstart_recommendations(st.session_state["liked_movies"])

    recos = st.session_state.get("recos")
    if recos:
        cols = st.columns(GRID_COLS)
        for i, movie in enumerate(recos):
            with cols[i % GRID_COLS]:
                tmdb_id = movie.get("tmdbId")
                raw_title = movie.get("title", "Untitled")
                title = display_title(raw_title)
                movie_id = movie.get("movieId")
                poster = movie.get("poster_url")

                if not tmdb_id:
                    st.caption(title)
                    continue

                st.button(
                    "▶",
                    key=f"rec_open_{tmdb_id}",
                    help=f"Open details: {title}",
                    on_click=select_movie,
                    args=(tmdb_id, movie_id, raw_title),
                    use_container_width=True,
                )
                if poster:
                    st.image(poster, use_container_width=True)
                st.caption(title)
    else:
        st.info("Click 'Get Recommendations' to see suggestions.")
