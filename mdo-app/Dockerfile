# MDO frontend — Next.js standalone build
FROM node:22-alpine AS builder
WORKDIR /app

# Electron is a devDependency for the desktop build only — skip its 100MB binary
ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1 \
    NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Baked into the client bundle at build time — must be the URL the BROWSER
# can reach (VPS public IP or domain), not localhost inside the container.
ARG NEXT_PUBLIC_API_URL=http://localhost:8501
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
