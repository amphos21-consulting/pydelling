"""Local HTTP + Server-Sent Events server for the dashboard (stdlib only).

Bound to 127.0.0.1. Static files need no token; every ``/api`` call requires the
per-session token (``Authorization: Bearer`` or ``?token=`` for EventSource), a
``Host`` header naming this server (DNS-rebinding guard) and JSON bodies on POST.
"""

import hmac
import json
import mimetypes
import re
import secrets
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .service import NotFound
from .transport import TransportError

STATIC = Path(__file__).with_name("static")
CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
STREAM_POLL_SECONDS = 0.5
KEEPALIVE_SECONDS = 15.0


def _flag(value):
    return str(value).lower() in ("1", "true", "yes")


ROUTES = [
    (
        "GET",
        r"/api/overview",
        lambda s, m, q, b: s.overview(
            status=q.get("status"), host=q.get("host"), q=q.get("q"), active=_flag(q.get("active"))
        ),
    ),
    ("GET", r"/api/hosts", lambda s, m, q, b: s.hosts()),
    ("GET", r"/api/entries", lambda s, m, q, b: s.entries()),
    (
        "GET",
        r"/api/preview",
        lambda s, m, q, b: s.preview(q.get("entry"), q.get("path"), q.get("host") or None),
    ),
    ("GET", r"/api/runs/(?P<run>[0-9a-f]{1,64})", lambda s, m, q, b: s.run_detail(m["run"])),
    (
        "GET",
        r"/api/runs/(?P<run>[^/]+)/events",
        lambda s, m, q, b: s.events(m["run"], int(q.get("after", 0))),
    ),
    (
        "GET",
        r"/api/runs/(?P<run>[^/]+)/log",
        lambda s, m, q, b: s.worker_log(m["run"], live=_flag(q.get("live"))),
    ),
    ("GET", r"/api/runs/(?P<run>[^/]+)/tables", lambda s, m, q, b: s.tables(m["run"])),
    (
        "GET",
        r"/api/runs/(?P<run>[^/]+)/table",
        lambda s, m, q, b: s.table(
            m["run"],
            q.get("path"),
            offset=int(q.get("offset", 0)),
            limit=int(q.get("limit", 100)),
            query=q.get("q", ""),
        ),
    ),
    (
        "GET",
        r"/api/runs/(?P<run>[^/]+)/studies/(?P<study>[^/]+)",
        lambda s, m, q, b: s.study(m["run"], m["study"]),
    ),
    (
        "GET",
        r"/api/runs/(?P<run>[^/]+)/studies/(?P<study>[^/]+)/log",
        lambda s, m, q, b: s.study_log(m["run"], m["study"], q.get("stream", "stdout")),
    ),
    ("POST", r"/api/hosts/(?P<host>[^/]+)/preflight", lambda s, m, q, b: s.preflight(m["host"])),
    ("POST", r"/api/hosts/(?P<host>[^/]+)/reconnect", lambda s, m, q, b: s.reconnect(m["host"])),
    (
        "POST",
        r"/api/history/clear",
        lambda s, m, q, b: s.clear_history(files=b.get("files") is True),
    ),
    (
        "POST",
        r"/api/runs/(?P<run>[^/]+)/delete",
        lambda s, m, q, b: s.delete(m["run"], files=b.get("files") is True),
    ),
    ("POST", r"/api/launch", lambda s, m, q, b: s.launch(b)),
    ("POST", r"/api/runs/(?P<run>[^/]+)/cancel", lambda s, m, q, b: s.cancel(m["run"])),
    ("POST", r"/api/runs/(?P<run>[^/]+)/resume", lambda s, m, q, b: s.resume(m["run"])),
    (
        "POST",
        r"/api/runs/(?P<run>[^/]+)/collect",
        lambda s, m, q, b: s.collect(m["run"], raw=bool(b.get("raw")), full_logs=bool(b.get("full_logs"))),
    ),
    ("POST", r"/api/runs/(?P<run>[^/]+)/open", lambda s, m, q, b: s.open_folder(m["run"])),
]
COMPILED = [(method, re.compile(pattern + r"/?"), handler) for method, pattern, handler in ROUTES]


class Handler(BaseHTTPRequestHandler):
    server_version = "pydelling-monitor"
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        if self.server.verbose:
            super().log_message(format, *args)

    # Guards ----------------------------------------------------------------------------
    def _host_ok(self):
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        return self.headers.get("Host", "") in allowed

    def _token_ok(self, query):
        header = self.headers.get("Authorization", "")
        supplied = header[7:] if header.startswith("Bearer ") else query.get("token", "")
        return hmac.compare_digest(supplied.encode(), self.server.token.encode())

    def _send(self, status, body, content_type="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, status, value):
        self._send(status, json.dumps(value, default=str, allow_nan=False))

    def _error(self, status, message):
        self._json(status, {"error": message})

    # Dispatch --------------------------------------------------------------------------
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "Host no permitido")
        url = urlsplit(self.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        if not url.path.startswith("/api/"):
            return self._static(url.path) if method == "GET" else self._error(405, "Método")
        if not self._token_ok(query):
            return self._error(HTTPStatus.UNAUTHORIZED, "Token de sesión requerido")
        if method == "GET" and url.path.rstrip("/") == "/api/stream":
            return self._stream(query)
        body = {}
        if method == "POST":
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Se espera JSON")
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._error(HTTPStatus.BAD_REQUEST, "JSON inválido")
            if not isinstance(body, dict):
                return self._error(HTTPStatus.BAD_REQUEST, "Se espera un objeto JSON")
        for route_method, pattern, handler in COMPILED:
            match = pattern.fullmatch(url.path)
            if route_method == method and match:
                try:
                    return self._json(200, handler(self.server.service, match, query, body))
                except NotFound as exc:
                    return self._error(HTTPStatus.NOT_FOUND, str(exc))
                except (ValueError, KeyError) as exc:
                    return self._error(HTTPStatus.BAD_REQUEST, str(exc))
                except TransportError as exc:
                    return self._error(HTTPStatus.BAD_GATEWAY, str(exc))
                except RuntimeError as exc:
                    return self._error(HTTPStatus.CONFLICT, str(exc))
        return self._error(HTTPStatus.NOT_FOUND, "Ruta desconocida")

    def _static(self, path):
        relative = "index.html" if path in ("/", "/index.html") else path.removeprefix("/static/")
        if path not in ("/", "/index.html") and not path.startswith("/static/"):
            return self._error(HTTPStatus.NOT_FOUND, "No encontrado")
        target = (STATIC / relative).resolve()
        if not target.is_relative_to(STATIC.resolve()) or not target.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "No encontrado")
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind.endswith("javascript"):
            kind += "; charset=utf-8"
        self._send(200, target.read_bytes(), kind)

    def _stream(self, query):
        try:
            rev = int(query.get("rev", 0))
            event_id = int(query.get("event_id", 0))
        except ValueError:
            return self._error(HTTPStatus.BAD_REQUEST, "Cursor inválido")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        service = self.server.service

        def frame(event, data):
            payload = json.dumps(data, default=str, allow_nan=False)
            self.wfile.write(f"event: {event}\ndata: {payload}\n\n".encode())
            self.wfile.flush()

        try:
            frame("ready", {"rev": rev, "event_id": event_id})
            quiet = time.monotonic()
            while not self.server.stopping:
                data = service.changes(rev, event_id)
                if (
                    data.get("deleted_runs")
                    or data["hosts"]
                    or data["runs"]
                    or data["studies"]
                    or data["events"]
                ):
                    frame("changes", data)
                    quiet = time.monotonic()
                elif time.monotonic() - quiet > KEEPALIVE_SECONDS:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    quiet = time.monotonic()
                rev, event_id = data["rev"], data["event_id"]
                time.sleep(STREAM_POLL_SECONDS)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return


class MonitorServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service, token, verbose=False):
        super().__init__(address, Handler)
        self.service = service
        self.token = token
        self.verbose = verbose
        self.stopping = False

    def shutdown(self):
        self.stopping = True
        super().shutdown()


def make_server(service, port=8765, token=None, verbose=False):
    token = token or secrets.token_urlsafe(24)
    return MonitorServer(("127.0.0.1", port), service, token, verbose), token


def serve(service, port=8765, open_browser=True, verbose=False):
    server, token = make_server(service, port=port, verbose=verbose)
    url = f"http://127.0.0.1:{server.server_address[1]}/#token={token}"
    print(f"Monitor de runs en {url}", flush=True)
    print("Ctrl+C para detenerlo. Los workers remotos siguen ejecutándose.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return url
