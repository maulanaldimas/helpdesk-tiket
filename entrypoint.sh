#!/bin/sh
set -e

echo ">> Menjalankan migrasi database..."
python manage.py migrate --noinput

echo ">> Mengumpulkan static files..."
python manage.py collectstatic --noinput

echo ">> Menjalankan server..."
exec "$@"
