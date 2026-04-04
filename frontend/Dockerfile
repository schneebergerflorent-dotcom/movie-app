FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your Streamlit code
COPY . .

# Cloud Run sets $PORT automatically
ENV PORT=8080

CMD ["sh", "-c", "streamlit run streamlit_app.py \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.address=0.0.0.0 \
    --server.port=$PORT"]