# One image for all three sites. Choose the site with the SIDE environment
# variable: management (default), teacher or student.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SIDE=management

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render injects PORT; 10000 is Render's default.
EXPOSE 10000
CMD ["sh", "-c", "gunicorn --chdir ${SIDE}_side -w 1 --threads 4 --timeout 120 -b 0.0.0.0:${PORT:-10000} wsgi:app"]
