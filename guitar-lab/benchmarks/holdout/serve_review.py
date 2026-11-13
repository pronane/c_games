"""Serve only the local review UI. No audio upload endpoint or dataset access.

python -m benchmarks.holdout.serve_review [--port 8765]
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import ROOT


class ReviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?',1)[0] not in ('/','/review.html'):
            self.send_error(404);return
        body=(ROOT/'review.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(body)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8765)
    args=p.parse_args();ThreadingHTTPServer(('0.0.0.0',args.port),ReviewHandler).serve_forever()


if __name__=='__main__':main()
