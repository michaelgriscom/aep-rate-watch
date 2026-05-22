FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RATE_WATCH_STATE=/data/aep_rate_state.json

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aep_rate_watch.py .

RUN mkdir -p /data
VOLUME ["/data"]

CMD ["python", "/app/aep_rate_watch.py"]
