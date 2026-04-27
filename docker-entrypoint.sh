#!/bin/bash
set -e

# Wait for database to be ready
echo "Waiting for database..."
while ! python -c "import psycopg2; psycopg2.connect(host='db', database='stellar', user='stellar', password='stellar')" 2>/dev/null; do
  sleep 1
done
echo "Database is ready!"

# Run migrations
echo "Running database migrations..."
python initialize.py || true

# Start the application
echo "Starting application..."
# GUNICORN_CMD_ARGS="--bind=0.0.0.0:9000" gunicorn --thread 4 wsgi:app
python run.py