import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
accesslog = "-"
errorlog = "-"

_json_access_log = (
    '{"event": "http.request", "method": "%(m)s", "path": "%(U)s", "query": "%(q)s", '
    '"status": %(s)s, "duration_seconds": %(L)s, "bytes": %(B)s, '
    '"request_id": "%({x-request-id}o)s", "referer": "%(f)s"}'
)
_text_access_log = '%(m)s %(U)s%(q)s %(s)s %(L)ss [%({x-request-id}o)s]'

access_log_format = (
    _json_access_log
    if os.environ.get("DJANGO_LOG_FORMAT", "text").lower() == "json"
    else _text_access_log
)
