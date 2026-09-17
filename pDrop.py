#!/usr/bin/env python3
"""pDrop — passworded LAN file browser for SharkDeck.

  pDrop                     # http://<deck-ip>:8080
  pDrop --root /home/working --port 8080 --pass secret

Password file: ~/.pdrop.pass  (one line) or --pass or env PDROP_PASS.
Stay on your LAN. This is HTTP, not HTTPS.
"""

from __future__ import annotations

import argparse
import base64
import html
import http.server
import os
import posixpath
import sys
import urllib.parse
from functools import partial

NAME = "pDrop"
DEFAULT_ROOT = "/home/working" if os.path.isdir("/home/working") else os.path.expanduser("~")
PASS_FILE = os.path.expanduser("~/.pdrop.pass")


def load_pass(cli: str | None) -> str:
    if cli:
        return cli
    env = os.environ.get("PDROP_PASS")
    if env:
        return env
    try:
        with open(PASS_FILE, encoding="utf-8") as fh:
            line = fh.readline().strip()
            if line:
                return line
    except OSError:
        pass
    return "shark"


def safe_join(root: str, rel: str) -> str:
    rel = urllib.parse.unquote(rel)
    rel = rel.replace("\\", "/")
    while rel.startswith("/"):
        rel = rel[1:]
    path = os.path.abspath(os.path.join(root, rel))
    root = os.path.abspath(root)
    if path != root and not path.startswith(root + os.sep):
        return root
    return path


def web_path(root: str, path: str) -> str:
    root = os.path.abspath(root)
    path = os.path.abspath(path)
    if path == root:
        return "/"
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    return "/" + rel


def fmt_size(n: int) -> str:
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.0f K" % (n / 1024)
    return "%.1f M" % (n / (1024 * 1024))


PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pDrop %s</title>
<style>
body{font:15px/1.4 system-ui,sans-serif;background:#111;color:#ddd;margin:0}
header{background:#1a1a1a;border-bottom:1px solid #333;padding:12px 16px}
h1{font-size:16px;margin:0;color:#6f6}
a{color:#8cf;text-decoration:none}
a:hover{text-decoration:underline}
main{padding:12px 16px 40px}
table{border-collapse:collapse;width:100%%;max-width:900px}
td,th{text-align:left;padding:6px 8px;border-bottom:1px solid #2a2a2a}
tr:hover td{background:#1c1c1c}
.dir a{color:#6f6}
.muted{color:#888;font-size:13px}
form.row{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
input[type=text],input[type=file]{background:#222;color:#eee;border:1px solid #444;padding:6px}
button{background:#262;color:#dfd;border:0;padding:6px 12px;cursor:pointer}
button.danger{background:#622}
.crumb{margin:0;font-size:13px;color:#888}
</style></head><body>
<header>
  <h1>pDrop</h1>
  <p class="crumb">%s</p>
</header>
<main>
%s
</main></body></html>
"""


def crumbs(wp: str) -> str:
    parts = [p for p in wp.split("/") if p]
    out = ['<a href="/">/</a>']
    acc = ""
    for p in parts:
        acc += "/" + p
        out.append(" / <a href=\"%s\">%s</a>" % (html.escape(acc, quote=True), html.escape(p)))
    return "".join(out)


def listing_html(root: str, path: str) -> str:
    wp = web_path(root, path)
    rows = []
    if wp != "/":
        parent = posixpath.dirname(wp.rstrip("/")) or "/"
        rows.append("<tr class=dir><td><a href=\"%s\">..</a></td><td></td><td></td></tr>" % html.escape(parent, True))
    try:
        names = sorted(os.listdir(path), key=lambda n: (not os.path.isdir(os.path.join(path, n)), n.lower()))
    except OSError as exc:
        names = []
        rows.append("<tr><td colspan=3 class=muted>%s</td></tr>" % html.escape(str(exc)))
    for name in names:
        full = os.path.join(path, name)
        href = web_path(root, full)
        try:
            st = os.stat(full)
            isdir = os.path.isdir(full)
            sz = "" if isdir else fmt_size(st.st_size)
        except OSError:
            continue
        cls = "dir" if isdir else "file"
        label = name + ("/" if isdir else "")
        del_form = (
            "<form method=post action=\"%s\" style=display:inline>"
            "<input type=hidden name=op value=del>"
            "<input type=hidden name=name value=\"%s\">"
            "<button class=danger>del</button></form>"
            % (html.escape(wp, True), html.escape(name, True))
        )
        rows.append(
            "<tr class=%s><td><a href=\"%s\">%s</a></td><td class=muted>%s</td><td>%s</td></tr>"
            % (cls, html.escape(href, True), html.escape(label), sz, del_form)
        )
    body = [
        "<table><tr><th>name</th><th>size</th><th></th></tr>",
        "".join(rows),
        "</table>",
        "<form class=row method=post action=\"%s\" enctype=multipart/form-data>" % html.escape(wp, True),
        "<input type=hidden name=op value=up>",
        "<input type=file name=file>",
        "<button>upload</button></form>",
        "<form class=row method=post action=\"%s\">" % html.escape(wp, True),
        "<input type=hidden name=op value=mkdir>",
        "<input type=text name=name placeholder=new-folder>",
        "<button>mkdir</button></form>",
    ]
    return PAGE % (html.escape(wp), crumbs(wp), "\n".join(body))


class Handler(http.server.BaseHTTPRequestHandler):
    root = DEFAULT_ROOT
    password = "shark"
    user = "pdrop"

    def log_message(self, fmt, *args):
        sys.stderr.write("pDrop: " + (fmt % args) + "\n")

    def auth_ok(self) -> bool:
        hdr = self.headers.get("Authorization", "")
        if not hdr.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(hdr.split(" ", 1)[1]).decode("utf-8")
        except Exception:
            return False
        if ":" not in raw:
            return False
        u, p = raw.split(":", 1)
        return u == self.user and p == self.password

    def need_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="pDrop"')
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"password required")

    def send_html(self, body: str, code: int = 200):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, loc: str):
        self.send_response(303)
        self.send_header("Location", loc)
        self.end_headers()

    def do_GET(self):
        if not self.auth_ok():
            self.need_auth()
            return
        parsed = urllib.parse.urlparse(self.path)
        path = safe_join(self.root, parsed.path)
        if os.path.isdir(path):
            self.send_html(listing_html(self.root, path))
            return
        if not os.path.isfile(path):
            self.send_html("<h1>not found</h1>", 404)
            return
        try:
            size = os.path.getsize(path)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename=\"%s\"" % os.path.basename(path).replace('"', ""))
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except OSError as exc:
            self.send_html(html.escape(str(exc)), 500)

    def do_POST(self):
        if not self.auth_ok():
            self.need_auth()
            return
        parsed = urllib.parse.urlparse(self.path)
        path = safe_join(self.root, parsed.path)
        if not os.path.isdir(path):
            self.send_html("not a directory", 400)
            return
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""

        if "multipart/form-data" in ctype:
            self._upload(path, ctype, raw)
            self.redirect(web_path(self.root, path))
            return

        fields = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
        op = (fields.get("op") or [""])[0]
        name = (fields.get("name") or [""])[0].strip()
        name = os.path.basename(name.replace("\\", "/"))
        if op == "mkdir" and name:
            try:
                os.mkdir(os.path.join(path, name))
            except OSError as exc:
                self.send_html(html.escape(str(exc)), 400)
                return
        elif op == "del" and name:
            target = safe_join(self.root, os.path.join(web_path(self.root, path), name).lstrip("/"))
            try:
                if os.path.isdir(target):
                    os.rmdir(target)
                else:
                    os.remove(target)
            except OSError as exc:
                self.send_html(html.escape(str(exc)), 400)
                return
        self.redirect(web_path(self.root, path))

    def _upload(self, dest_dir: str, ctype: str, raw: bytes):
        bound = ""
        for part in ctype.split(";"):
            part = part.strip()
            if part.lower().startswith("boundary="):
                bound = part.split("=", 1)[1].strip().strip('"')
        if not bound:
            return
        token = b"--" + bound.encode("ascii", "replace")
        chunks = raw.split(token)
        for chunk in chunks:
            if chunk in (b"", b"--", b"--\r\n", b"\r\n"):
                continue
            if chunk.startswith(b"--"):
                continue
            if chunk.startswith(b"\r\n"):
                chunk = chunk[2:]
            if b"\r\n\r\n" not in chunk:
                continue
            head, body = chunk.split(b"\r\n\r\n", 1)
            if body.endswith(b"\r\n"):
                body = body[:-2]
            header = head.decode("utf-8", "replace")
            fname = ""
            for line in header.split("\r\n"):
                if "filename=" in line:
                    fname = line.split("filename=", 1)[1].strip().strip('"')
            fname = os.path.basename(fname.replace("\\", "/"))
            if not fname:
                continue
            out = safe_join(self.root, os.path.join(web_path(self.root, dest_dir), fname).lstrip("/"))
            with open(out, "wb") as fh:
                fh.write(body)


def main() -> int:
    p = argparse.ArgumentParser(prog="pDrop")
    p.add_argument("--root", default=DEFAULT_ROOT)
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--pass", dest="password", default=None)
    p.add_argument("--user", default="pdrop")
    args = p.parse_args()
    root = os.path.abspath(os.path.expanduser(args.root))
    os.makedirs(root, exist_ok=True)
    Handler.root = root
    Handler.password = load_pass(args.password)
    Handler.user = args.user
    httpd = http.server.ThreadingHTTPServer((args.bind, args.port), Handler)
    print("pDrop  http://%s:%d/  root=%s  user=%s" % (args.bind, args.port, root, args.user), flush=True)
    print("set a real password in ~/.pdrop.pass", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
