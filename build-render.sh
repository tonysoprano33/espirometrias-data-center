#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt gunicorn==23.0.0
python src/manage.py collectstatic --noinput
