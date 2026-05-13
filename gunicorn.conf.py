bind = "127.0.0.1:8000"

workers = 1
threads = 4
worker_class = "gthread"

timeout = 120
graceful_timeout = 30
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = "info"
capture_output = True

proc_name = "thunder_trading"

limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
