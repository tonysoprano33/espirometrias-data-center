#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python src/manage.py collectstatic --noinput
