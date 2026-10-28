#!/usr/bin/env python3
"""Static server for the Arena FC web build.
Godot 4 Web exports need COOP/COEP headers for SharedArrayBuffer (threaded builds).
This build is single-threaded, but the headers are set anyway for compatibility.
"""
import argparse, functools, http.server, socketserver, os

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()
    def guess_type(self, path):
        if path.endswith(".wasm"): return "application/wasm"
        if path.endswith(".pck"): return "application/octet-stream"
        if path.endswith(".js"): return "application/javascript"
        return super().guess_type(path)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--dir", default=os.path.dirname(__file__))
    a = ap.parse_args()
    os.chdir(a.dir)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", a.port), Handler) as httpd:
        print(f"Arena FC web build: http://localhost:{a.port}/  (Ctrl+C to stop)", flush=True)
        httpd.serve_forever()
