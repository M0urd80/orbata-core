FROM python:3.11

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh

# Migrations first; on failure entrypoint exits 1 with a clear log (see docker-entrypoint.sh).
ENTRYPOINT ["./docker-entrypoint.sh"]
