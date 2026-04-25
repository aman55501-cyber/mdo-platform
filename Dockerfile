FROM python:3.11-slim

WORKDIR /app

# ffmpeg needed by yt-dlp for audio extraction; gcc for faster-whisper build
RUN apt-get update && apt-get install -y --no-install-recommends gcc ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements_server.txt ./
RUN pip install --no-cache-dir -r requirements_server.txt

COPY mdo_server.py ./

# /data is mounted as a Railway persistent volume — SQLite lives here
ENV VEGA_DB_PATH=/data/vega_data.db
ENV VEDANTA_DB_PATH=/data/vedanta_crm.db

EXPOSE 8501

CMD ["python", "mdo_server.py"]
