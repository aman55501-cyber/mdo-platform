FROM python:3.11-slim

WORKDIR /app

# ffmpeg needed by yt-dlp for audio extraction; gcc for faster-whisper build
# tzdata so TZ=Asia/Kolkata gives correct IST market hours
# poppler-utils: pdftotext -layout for Angel One DP statements (pypdf is the fallback)
RUN apt-get update && apt-get install -y --no-install-recommends gcc ffmpeg tzdata openssl poppler-utils \
    && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Kolkata

COPY requirements_server.txt ./
RUN pip install --no-cache-dir -r requirements_server.txt

# Every top-level module ships; a new mdo_*.py must never be left out of the image again.
COPY *.py ./
COPY fleet.yaml agenda.yaml CHIEF_OF_STAFF.md DEPLOY_HOSTINGER.md .env.example deploy_vps.sh ./
COPY tests ./tests
COPY tools ./tools
COPY data ./data
COPY briefs ./briefs

# /data is mounted as a Railway persistent volume — SQLite lives here
ENV VEGA_DB_PATH=/data/vega_data.db
ENV VEDANTA_DB_PATH=/data/vedanta_crm.db

EXPOSE 8501

CMD ["python", "mdo_server.py"]
