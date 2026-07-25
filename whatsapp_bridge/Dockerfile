# MDO WhatsApp bridge — Baileys (WebSocket), no Chromium required
FROM node:20-slim

WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY index.js ./

# WhatsApp session credentials persist here (docker volume)
ENV AUTH_DIR=/data/wa_auth

EXPOSE 3001
CMD ["node", "index.js"]
