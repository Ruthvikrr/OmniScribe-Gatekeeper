import threading
import time
import sys
import os

# Ensure project root is on sys.path so 'backend' imports resolve
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.oauth_server import start_oauth_server, build_auth_url, connect_service
from flask import Flask

# Start OAuth server (blocks) in its own thread
t1 = threading.Thread(target=start_oauth_server, daemon=True)
t1.start()

# Start simple connect helper
_connect_app = Flask("connect_helper")

@_connect_app.route('/connect/<service>')
def _handle_connect(service):
    return connect_service(service)

# Run connect helper (blocking)
_connect_app.run(port=7862, debug=False, use_reloader=False)
