# Movie Explorer

This project is a Streamlit web application that allows users to explore movies using filters such as title, genre, language, rating, and release year.  
The data comes from Google BigQuery, and additional movie details (poster, cast, overview) are retrieved from the TMDB API.  
The application is containerized with Docker and deployed on Google Cloud Run.

## Live Application
link : https://movie-app-714848336619.europe-west6.run.app/

## How to Run Locally
Install dependencies:
    pip install -r requirements.txt

Run the app:
    streamlit run app.py

## Run with Docker
Build the image:
    docker build -t movie-app .

Run the container:
    docker run -p 8080:8080 movie-app


## Note
This assignment was completed with the assistance of Copilot. 
