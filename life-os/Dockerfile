FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent volume for the JSON store — mount here in production so the board
# survives redeploys. Matches LIFE_STATE_DIR's default.
ENV LIFE_STATE_DIR=/app/data/state/life
VOLUME ["/app/data/state/life"]

EXPOSE 8600
CMD ["python", "app.py"]
