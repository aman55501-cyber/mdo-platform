# MDO WhatsApp bridge — Baileys (WebSocket), no Chromium required
FROM node:20-slim

# Baileys installs one dependency from a git URL — slim images lack git
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY index.js ./

# WhatsApp session credentials persist here (docker volume)
ENV AUTH_DIR=/data/wa_auth

EXPOSE 3001
CMD ["node", "index.js"]
