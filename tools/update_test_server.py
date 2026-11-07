"""A local update server for the Windows update journeys (#45, CI only).

Serves one of several prepared folders (``good``, ``tampered``, ``older``)
on http://127.0.0.1:<port>/ with HTTP Range support, and can damage or
interrupt the installer download on request. Test builds accept this
address only because their build_info.json names it (channel "test");
distributed builds accept GitHub over HTTPS only.

    python tools/update_test_server.py <root> --port 8765      # standalone
"""

from __future__ import annotations

import argparse
import http.server
import threading
from pathlib import Path


class UpdateTestServer:
    def __init__(self, root: Path, port: int = 8765):
        self.root, self.port = Path(root), port
        self.scenario = "good"
        self.fault = None          # None | "corrupt" | "interrupt"
        self.requests: list[tuple[str, str | None]] = []
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                owner.requests.append((self.path, self.headers.get("Range")))
                name = self.path.lstrip("/").split("?")[0]
                path = owner.root / owner.scenario / name
                if not name or "/" in name or ".." in name or not path.is_file():
                    self.send_error(404)
                    return
                body = path.read_bytes()
                if owner.fault == "corrupt" and name.endswith(".exe"):
                    body = body[:-1] + bytes([body[-1] ^ 0xFF])
                start = 0
                wanted = self.headers.get("Range")
                if wanted and wanted.startswith("bytes="):
                    start = int(wanted[6:].split("-")[0] or 0)
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
                else:
                    self.send_response(200)
                part = body[start:]
                self.send_header("Content-Length", str(len(part)))
                self.end_headers()
                if owner.fault == "interrupt" and name.endswith(".exe"):
                    owner.fault = None                 # the retry succeeds
                    self.wfile.write(part[: len(part) // 3])
                    self.wfile.flush()
                    self.connection.shutdown(2)
                    return
                self.wfile.write(part)

        class Quiet(http.server.ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass

        self.httpd = Quiet(("127.0.0.1", port), Handler)

    def start(self) -> "UpdateTestServer":
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scenario", default="good")
    args = parser.parse_args(argv)
    server = UpdateTestServer(args.root, args.port)
    server.scenario = args.scenario
    print(f"serving {args.root / args.scenario} on http://127.0.0.1:{args.port}/", flush=True)
    server.httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
