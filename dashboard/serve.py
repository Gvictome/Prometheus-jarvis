"""Lightweight static file server for the Sports Signal Intelligence dashboard."""

import http.server
import os
import sys

PORT = 5500


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    handler = http.server.SimpleHTTPRequestHandler
    with http.server.HTTPServer(("0.0.0.0", PORT), handler) as httpd:
        print(f"Dashboard running at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")
            sys.exit(0)


if __name__ == "__main__":
    main()
