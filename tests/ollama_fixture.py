"""Deterministic HTTP provider for disposable CI only; never used by deployment."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import time

class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps({'models':[{'name':'qwen3:4b','size':2500000000}]}).encode())
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        if self.path!='/api/chat':
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
            self.wfile.write(json.dumps({'response':'OK','done':True}).encode());return
        self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.end_headers()
        for i,text in enumerate(('Deterministic ','streamed ','CI reply.')):
            time.sleep(.3)
            self.wfile.write((json.dumps({'message':{'role':'assistant','content':text},'done':i==2})+'\n').encode())
            self.wfile.flush()

if __name__=='__main__':
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise SystemExit('This provider fixture is restricted to disposable CI.')
    HTTPServer(('127.0.0.1',11434),Fixture).serve_forever()
