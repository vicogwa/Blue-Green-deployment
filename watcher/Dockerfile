FROM python:3.12-slim

WORKDIR /app

COPY watcher.py .

RUN pip install --no-cache-dir requests python-dateutil

CMD ["python", "-u", "watcher.py"]
