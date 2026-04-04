FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run injecte PORT. Il faut un shell pour expand ${PORT:-8080}
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-8080} Backend_app:app"]