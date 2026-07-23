# Business OS — standalone container (deploy target: Docker on Hostinger VPS)
FROM python:3.11-slim

WORKDIR /app

COPY business_os/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the package (keep the module path business_os.*)
COPY business_os/ ./business_os/

# Persistent volume: dataset JSON lives here. Mount a host dir / named volume:
#   docker run -v businessos_data:/data/state/business ...
ENV BUSINESS_DATA_DIR=/data/state/business
ENV PORT=8600
VOLUME ["/data/state/business"]

EXPOSE 8600

CMD ["python", "-m", "business_os"]
