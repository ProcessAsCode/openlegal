FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libxml2 libxslt1.1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app /app
COPY uas-data /uas-data
# Seed the mutable UAS tree (schema/rules/profiles/clause-library) into the
# data volume on first start; a mounted /data/uas wins if it already exists.
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV APP_DB_PATH=/data/db/eligumi.sqlite AGREEMENTS_ROOT=/data/agreements UAS_ROOT=/data/uas ELIGUMI_TENANT_SLUG=demo
EXPOSE 8050
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8050", "--proxy-headers", "--forwarded-allow-ips", "*"]
