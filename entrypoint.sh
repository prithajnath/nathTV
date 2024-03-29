#!/usr/bin/env bash
python manage.py db migrate
python manage.py db upgrade
gunicorn \
    -w $(nproc) \
    --bind 0.0.0.0:$PORT app:app