# ---------- Builder / runtime ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies (wheels sudah tersedia, tanpa build tools)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Aplikasi
COPY . .

# Direktori runtime
RUN mkdir -p /app/media /app/logs /app/staticfiles

# Entrypoint: pastikan line-ending LF walau di-clone dari Windows
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "helpdesk.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "--access-logfile", "-"]
