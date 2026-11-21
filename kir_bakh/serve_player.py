import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse, parse_qs

ROOT = os.path.abspath("kir_bakh")


class RangeHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self._serve(send_body=False)

    def do_GET(self):
        self._serve(send_body=True)

    def _serve(self, send_body: bool):
        parsed = urlparse(self.path)
        rel = unquote(parsed.path).lstrip("/")
        if rel == "" or rel == "index.html":
            rel = "player/index.html"

        target = os.path.abspath(os.path.join(ROOT, rel))
        if not target.startswith(ROOT + os.sep) or not os.path.isfile(target):
            self.send_error(404, "Not found")
            return

        size = os.path.getsize(target)
        ctype, _ = mimetypes.guess_type(target)
        if not ctype:
            ctype = "application/octet-stream"
        if target.endswith(".html"):
            ctype = "text/html; charset=utf-8"

        qs = parse_qs(parsed.query)
        range_hdr = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200

        if range_hdr:
            m = re.match(r"bytes=(\d*)-(\d*)", range_hdr.strip())
            if m:
                s_str, e_str = m.groups()
                if s_str:
                    start = int(s_str)
                elif e_str:
                    start = max(0, size - int(e_str))
                if e_str and s_str:
                    end = min(size - 1, int(e_str))
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = 206

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Access-Control-Allow-Origin", "*")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if "download" in qs:
            fname = os.path.basename(target)
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
        self.end_headers()

        if not send_body:
            return

        with open(target, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except BrokenPipeError:
                    break
                remaining -= len(chunk)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), RangeHandler)
    print("Listening on http://0.0.0.0:8080", flush=True)
    server.serve_forever()
