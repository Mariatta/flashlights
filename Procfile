release: python manage.py createcachetable && python manage.py migrate
web: gunicorn -c config/gunicorn.conf.py portal.wsgi:application --log-file -
# The minimum formation is web + worker: bin/worker serves every queue and
# runs beat embedded. The two below are optional, for larger instances.
worker: sh bin/worker
worker-media: celery -A portal worker -Q media --concurrency 1 --loglevel=info
worker-beat: celery -A portal beat --loglevel=info
