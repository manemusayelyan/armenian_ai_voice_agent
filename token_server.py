import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from livekit import api

load_dotenv()


class TokenHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path != "/token":
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        room = params.get("room", ["bank-support"])[0]
        identity = params.get("identity", ["user"])[0]

        token = (
            api.AccessToken(
                os.environ["LIVEKIT_API_KEY"],
                os.environ["LIVEKIT_API_SECRET"],
            )
            .with_identity(identity)
            .with_name(identity)
            .with_grants(api.VideoGrants(room_join=True, room=room))
            .to_jwt()
        )

        body = json.dumps({"token": token}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args) -> None:
        pass


if __name__ == "__main__":
    port = 8080
    print(f"Token server running at http://localhost:{port}/token")
    HTTPServer(("", port), TokenHandler).serve_forever()