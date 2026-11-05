"""Loopback-only UI. Mutations require both the local token and reviewed plan."""

import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import changes, service, theme

STATIC = Path(__file__).with_name("web")


class Server(HTTPServer):
    def __init__(self, paths, port=0):
        super().__init__(("127.0.0.1", port), Handler)
        self.paths = paths
        self.token = secrets.token_urlsafe(32)
        self.plans = {}
        self.origin = f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, *_args):
        pass  # Avoid logging local paths or configuration values.

    def respond(self, status, value, mime="application/json"):
        data = json.dumps(value).encode() if mime == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; "
                         "script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; frame-ancestors 'none'; "
                         "base-uri 'none'; form-action 'self'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self, api=False):
        if self.headers.get("Host") != urlsplit(self.server.origin).netloc:
            self.respond(403, {"error": "Only the local control center address is accepted."})
            return False
        if self.headers.get("Origin", self.server.origin) != self.server.origin:
            self.respond(403, {"error": "Cross-origin access is not allowed."})
            return False
        if api and not secrets.compare_digest(
                self.headers.get("X-Desktop-Theming-Token", ""), self.server.token):
            self.respond(403, {"error": "Reopen the local control center to continue."})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if not self.authorized(api=path.startswith("/api/")):
            return
        try:
            if path == "/api/overview":
                self.respond(200, service.overview(self.server.paths))
            elif path in ("/", "/app.js", "/style.css"):
                name, mime = {"/": ("index.html", "text/html"),
                              "/app.js": ("app.js", "text/javascript"),
                              "/style.css": ("style.css", "text/css")}[path]
                value = (STATIC / name).read_bytes()
                if path == "/":
                    value = value.replace(b"__TOKEN__", self.server.token.encode())
                self.respond(200, value, mime)
            else:
                self.respond(404, {"error": "Not found."})
        except (ValueError, OSError, UnicodeError) as exc:
            self.respond(400, {"error": str(exc)})

    def do_POST(self):
        if not self.authorized(api=True):
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 65536:
                raise ValueError("Request is empty or too large.")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Expected a JSON request.")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise TypeError("Expected an object.")
            path = urlsplit(self.path).path
            if path == "/api/preview":
                result = theme.palette(service.validate_profile(body))
            elif path == "/api/plan":
                result = service.make_plan(self.server.paths, body)
                if len(self.server.plans) >= 20:
                    self.server.plans.pop(next(iter(self.server.plans)))
                self.server.plans[result["id"]] = result
            elif path == "/api/apply":
                plan = self.server.plans.get(body.get("id"))
                if not plan or body.get("approved") is not True:
                    raise ValueError("Review and explicitly approve a current plan first.")
                result = service.apply_reviewed(self.server.paths, plan)
                self.server.plans.clear()
            elif path == "/api/undo":
                if body.get("approved") is not True or not isinstance(body.get("id"), str):
                    raise ValueError("Explicit approval and a transaction ID are required.")
                result = changes.undo(self.server.paths, body["id"])
                self.server.plans.clear()
            else:
                self.respond(404, {"error": "Not found."})
                return
            self.respond(200, result)
        except (ValueError, OSError, UnicodeError, TypeError) as exc:
            self.respond(400, {"error": str(exc)})


def serve(paths, *, port=0, open_browser=True):
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535.")
    with Server(paths, port) as server:
        print(f"Desktop Theming · {server.origin}\nLocal only. Ctrl+C to close.", flush=True)
        if open_browser:
            threading.Timer(0.2, webbrowser.open, args=(server.origin,)).start()
        server.serve_forever()
