FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY data/steam_events.json data/steam_events.json
COPY wsgi.py .
RUN useradd -r -u 10001 tracker && mkdir -p /srv/data && chown -R tracker /srv/data
USER tracker
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "3", "--threads", "4", "--access-logfile", "-", "wsgi:app"]
