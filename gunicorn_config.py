import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:9000")
workers = 1
worker_class = "sanic.worker.GunicornWorker"
pidfile = "gunicorn.pid"
max_requests = 300
