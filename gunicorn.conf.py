import multiprocessing

# Bind to 0.0.0.0 to allow external access
bind = "0.0.0.0:$PORT"

workers = 1


max_requests = 1000
max_requests_jitter = 50

worker_connections = 1000
preload_app = True
