#!/bin/sh
set -e

echo ">> Running database migrations..."
python manage.py migrate --noinput

echo ">> Collecting static files..."
python manage.py collectstatic --noinput

echo ">> Starting server on port ${PORT:-8000}..."
exec gunicorn helpdesk.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --timeout 120 \
    --access-logfile -
