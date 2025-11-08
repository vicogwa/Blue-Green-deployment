FROM python:3.12-slim

WORKDIR /app

COPY alert_watcher.py .

RUN pip install --no-cache-dir requests

CMD ["python", "-u", "alert_watcher.py"]
