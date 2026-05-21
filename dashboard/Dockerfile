FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Backend URL — override at runtime with:
#   docker run -e BACKEND_URL=https://your-backend/api/v1 ...
#   or set in Cloud Run environment variables
ENV BACKEND_URL=https://ambient-climate-backend-977755576323.europe-west6.run.app/api/v1
ENV DEVICE_ID=m5stack-duska-home
ENV PORT=8080

# Streamlit requires a config dir; write a minimal one at build time
RUN mkdir -p /root/.streamlit && \
    printf '[server]\nheadless = true\nport = %s\nenableCORS = false\nenableXsrfProtection = false\n' "$PORT" \
    > /root/.streamlit/config.toml

EXPOSE 8080

CMD streamlit run app.py \
    --server.port=$PORT \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false
