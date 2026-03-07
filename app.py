import streamlit as st
import pandas as pd
from google.cloud import bigquery
from tmdb_api import get_movie_details

st.set_page_config(
    page_title="Movie Explorer",
    page_icon="🎬",
)

# --- Session defaults ---
if "selected_movie_id" not in st.session_state:
    st.session_state["selected_movie_id"] = None
if "selected_title" not in st.session_state:
    st.session_state["selected_title"] = None
if "last_results" not in st.session_state:
    st.session_state["last_results"] = None

# Initialize BigQuery client
client = bigquery.Client()

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

# ---------- QUERY FUNCTIONS ----------

def search_movies_by_release_year(min_year):
    sql = """
        SELECT 
            movieId,
            title,
            release_year
        FROM `assignment1-489216.movies_dataset.movies`
        WHERE release_year IS NOT NULL 
        AND release_year >= @min_year
        ORDER BY ABS(CAST(release_year AS INT64) - @min_year) ASC, release_year DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("min_year", "INT64", int(min_year))
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def search_movies_by_min_rating(min_rating):
    sql = """
        SELECT
            m.movieId,
            m.title,
            AVG(r.rating) AS avg_rating,
            COUNT(r.rating) AS rating_count
        FROM `assignment1-489216.movies_dataset.movies` AS m
        JOIN `assignment1-489216.movies_dataset.ratings` AS r
            ON m.movieId = r.movieId
        GROUP BY m.movieId, m.title
        HAVING AVG(r.rating) >= @min_rating
        ORDER BY (AVG(r.rating) * LN(COUNT(r.rating) + 1)) DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("min_rating", "FLOAT64", float(min_rating))
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def search_movies_by_genre(genre):
    sql = """
        SELECT movieId, title, genres
        FROM `assignment1-489216.movies_dataset.movies`
        WHERE LOWER(genres) LIKE LOWER(CONCAT('%', @genre, '%'))
        ORDER BY title
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("genre", "STRING", genre)
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def get_all_genres():
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
        SELECT movieId, title, language
        FROM `assignment1-489216.movies_dataset.movies`
        WHERE language = @language
        ORDER BY title
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("language", "STRING", language)
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def search_titles_startswith(prefix):
    sql = """
        SELECT movieId, title
        FROM `assignment1-489216.movies_dataset.movies`
        WHERE LOWER(title) LIKE LOWER(CONCAT(@prefix, '%'))
        ORDER BY title
        LIMIT 500
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("prefix", "STRING", prefix)
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def search_titles_contains(prefix):
    sql = """
        SELECT movieId, title
        FROM `assignment1-489216.movies_dataset.movies`
        WHERE LOWER(title) LIKE LOWER(CONCAT('%', @prefix, '%'))
        ORDER BY title
        LIMIT 500
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("prefix", "STRING", prefix)
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


# ---------- CACHED TMDB WRAPPER ----------

@st.cache_data(show_spinner=False)
def cached_get_movie_details(tmdb_id):
    return get_movie_details(tmdb_id)

# ---------- HELPERS FOR DETAILS DISPLAY ----------

def display_movie_details(tmdb_id):
    """
    Fetch and display TMDB movie details.
    Handles poster, metadata, cast, and missing data gracefully.
    """
    if not tmdb_id:
        return

    try:
        with st.spinner("Loading movie details..."):
            details = cached_get_movie_details(tmdb_id)
    except Exception as e:
        st.error("Unable to retrieve movie details at the moment.")
        st.write(f"Error: {e}")
        return

    poster_url = None

    if details.get("poster"):
        poster_url = details.get("poster")
    elif details.get("poster_path"):
        poster_url = f"https://image.tmdb.org/t/p/w500{details['poster_path']}"
    elif details.get("poster_url"):
        poster_url = details.get("poster_url")

    if poster_url and poster_url.startswith("http://"):
        poster_url = poster_url.replace("http://", "https://", 1)

    st.markdown("---")
    col1, col2 = st.columns([1, 2])
    with col1:
        if poster_url:
            st.image(poster_url, use_container_width=True)
        else:
            st.write("No poster available.")
    with col2:
        st.subheader(details.get("title", "Unknown title"))
        st.write(f"**Release date:** {details.get('release_date', 'Unknown')}")
        genres = details.get("genres") or []
        if genres:
            st.write(f"**Genres:** {', '.join(genres)}")
        st.write("**Overview:**")
        st.write(details.get("overview") or "No overview available.")
        cast = details.get("cast") or []
        if cast:
            st.write("**Top cast:**")
            st.write(", ".join(cast))
    st.markdown("---")


def movie_selector_block(df, label="Select a movie:", selectbox_key="movie_select"):
    """
    Displays a selectbox of movie titles and shows TMDB details when selected.
    Uses tmdbId instead of movieId to ensure correct posters and metadata.
    """
    if df.empty:
        return

    # FIX: map title -> tmdbId
    title_to_id = {row.title: row.tmdbId for _, row in df.iterrows()}
    titles = ["-- select --"] + sorted(title_to_id.keys())

    prev_title = st.session_state.get("selected_title")
    default_index = titles.index(prev_title) if prev_title in titles else 0

    selected_title = st.selectbox(label, titles, index=default_index, key=selectbox_key)

    if selected_title != "-- select --":
        tmdb_id = title_to_id[selected_title]
        if st.session_state.get("selected_movie_id") != tmdb_id:
            st.session_state["selected_movie_id"] = tmdb_id
            st.session_state["selected_title"] = selected_title
        display_movie_details(tmdb_id)

# ---------- UI (Home acts as unified Research) ----------

st.title("Welcome to Movie Explorer")
st.subheader("Research")
st.write("Activate the filters you want, then click Run Research.")

# --- Deep Research filters (Home) ---
title_query = st.text_input("Search by movie title (optional):", key="deep_title")

use_language = st.checkbox("Filter by language", key="deep_use_language")
use_genre = st.checkbox("Filter by genre", key="deep_use_genre")
use_rating = st.checkbox("Filter by minimum rating", key="deep_use_rating")
use_year = st.checkbox("Filter by release year (after selected year)", key="deep_use_year")

language_choice = None
genre_choice = None
min_rating = None
min_year = None

if use_language:
    langs_df = get_all_languages()
    languages = langs_df["language"].tolist()
    language_labels = [
		f"{code}: {LANGUAGE_NAMES.get(code, 'Unknown')}"
		for code in languages
]
    selected_label = st.selectbox("Select language:", ["-- select --"] + language_labels, key="deep_lang_select")
    if selected_label != "-- select --":
        language_choice = selected_label.split(":")[0].strip()

if use_genre:
    genres_df = get_all_genres()
    genres = genres_df["genre"].tolist()
    genre_choice = st.selectbox("Select genre:", ["-- select --"] + genres, key="deep_genre_select")
    if genre_choice != "-- select --":
        genre_choice = genre_choice

if use_rating:
    min_rating = st.slider("Minimum average rating:", 0.0, 5.0, 4.0, 0.1, key="deep_min_rating")

if use_year:
    min_year = st.number_input("Show movies released after:", 1890, 2026, 2019, key="deep_min_year")

run_clicked = st.button("Run Research", key="deep_run_btn")

if run_clicked:
    sql = """
        SELECT 
            m.movieId,
            m.title,
            m.language,
            m.genres,
            m.release_year,
            m.tmdbId
        FROM `assignment1-489216.movies_dataset.movies` AS m
    """

    if use_rating:
        sql += """
            JOIN `assignment1-489216.movies_dataset.ratings` AS r
            ON m.movieId = r.movieId
        """

    conditions = []

    if title_query:
        conditions.append("LOWER(m.title) LIKE LOWER(CONCAT('%', @title, '%'))")

    if use_language and language_choice:
        conditions.append("m.language = @language")

    if use_genre and genre_choice:
        conditions.append("LOWER(m.genres) LIKE LOWER(CONCAT('%', @genre, '%'))")

    if use_year and min_year is not None:
        conditions.append("CAST(m.release_year AS INT64) > @min_year")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    if use_rating:
        sql += """
            GROUP BY 
                m.movieId, m.title, m.language, m.genres, m.release_year, m.tmdbId
        """
        sql += " HAVING AVG(r.rating) >= @min_rating"

    if use_year:
        sql += " ORDER BY m.release_year DESC"
    elif use_rating:
        sql += " ORDER BY AVG(r.rating) DESC"
    else:
        sql += " ORDER BY m.title"

    params = []

    if title_query:
        params.append(bigquery.ScalarQueryParameter("title", "STRING", title_query))

    if use_language and language_choice:
        params.append(bigquery.ScalarQueryParameter("language", "STRING", language_choice))

    if use_genre and genre_choice:
        params.append(bigquery.ScalarQueryParameter("genre", "STRING", genre_choice))

    if use_rating and min_rating is not None:
        params.append(bigquery.ScalarQueryParameter("min_rating", "FLOAT64", float(min_rating)))

    if use_year and min_year is not None:
        params.append(bigquery.ScalarQueryParameter("min_year", "INT64", int(min_year)))

    job_config = bigquery.QueryJobConfig(query_parameters=params)

    df = client.query(sql, job_config=job_config).to_dataframe()

    if df is None or df.empty:
        st.session_state["last_results"] = None
        st.warning("No movies match your criteria.")
    else:
        st.session_state["last_results"] = df.to_dict(orient="records")
        st.success(f"Found {len(df)} matching movies.")

if st.session_state.get("last_results"):
    df_last = pd.DataFrame(st.session_state["last_results"])
    if not df_last.empty:
        movie_selector_block(df_last, label="Select a movie from results:", selectbox_key="deep_movie_select")
