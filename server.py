#!/usr/bin/env python3
"""Tiny website health-check backend for the homelab.

Does the fetch SERVER-SIDE so the browser's CORS / mixed-content rules don't
get in the way when probing arbitrary external sites. Python stdlib only.

  GET /check?url=<url>  -> JSON {ok, up, status, latency_ms, final_url,
                                 server, error}

nginx proxies /webcheck/ here, so the browser calls /webcheck/check
same-origin. No published port — only the web container reaches it.
"""
import ipaddress
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TIMEOUT = 10          # seconds before we call a site unreachable
UA = "homelab-healthcheck/1.0 (+tailnet)"


def normalize(url):
    """Add a scheme if missing; reject anything that isn't plain http(s)."""
    url = (url or "").strip()
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    return url


def host_is_public(host):
    """SSRF guard: resolve the host and require EVERY resolved address to be
    globally routable. Blocks loopback, RFC1918/private, link-local (incl. the
    169.254.169.254 metadata IP), CGNAT/tailnet, multicast and reserved ranges —
    so this checker can't be used to probe internal homelab services."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            return False
    return True


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Re-validate the target of every redirect, so a public URL can't bounce
    us to an internal address (redirect-based SSRF)."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_is_public(urlparse(newurl).hostname):
            raise urllib.error.URLError("redirect to non-public address blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(SafeRedirect)


def check(url):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA})
    start = time.monotonic()
    try:
        with _opener.open(req, timeout=TIMEOUT) as r:
            ms = round((time.monotonic() - start) * 1000)
            return {"ok": True, "up": True, "status": r.status, "latency_ms": ms,
                    "final_url": r.geturl(), "server": r.headers.get("Server", ""),
                    "error": None}
    except urllib.error.HTTPError as e:
        # The server answered — it's reachable. <500 = healthy-ish, 5xx = down.
        ms = round((time.monotonic() - start) * 1000)
        return {"ok": e.code < 400, "up": e.code < 500, "status": e.code,
                "latency_ms": ms, "final_url": url,
                "server": (e.headers.get("Server", "") if e.headers else ""),
                "error": None}
    except (urllib.error.URLError, socket.timeout, ssl.SSLError,
            ConnectionError, OSError) as e:
        ms = round((time.monotonic() - start) * 1000)
        reason = getattr(e, "reason", e)
        return {"ok": False, "up": False, "status": None, "latency_ms": ms,
                "final_url": url, "server": "", "error": str(reason)[:200]}
    except Exception as e:  # noqa: BLE001 — never 500 the checker itself
        return {"ok": False, "up": False, "status": None, "latency_ms": None,
                "final_url": url, "server": "", "error": str(e)[:200]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body=b""):
        self.send_response(code)
        if body:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        parts = urlparse(self.path)
        if parts.path.rstrip("/") != "/check":
            self._send(404)
            return
        raw = parse_qs(parts.query).get("url", [""])[0]
        url = normalize(raw)
        if not url:
            self._send(400, json.dumps(
                {"ok": False, "up": False, "error": "enter a valid http(s) URL"}
            ).encode())
            return
        if not host_is_public(urlparse(url).hostname):
            self._send(200, json.dumps({
                "ok": False, "up": False, "status": None, "latency_ms": None,
                "final_url": url, "server": "",
                "error": "blocked — not a public address (SSRF protection)"
            }).encode())
            return
        result = check(url)
        self._send(200, json.dumps(result).encode())

    def log_message(self, *args):
        pass  # quiet — keep Dozzle/compose logs clean


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
