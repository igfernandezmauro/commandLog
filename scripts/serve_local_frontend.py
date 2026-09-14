from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import mimetypes

import boto3
from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"

GENERATED_BUCKET = "commandlog-local-generated"

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:4566",
    region_name="ca-central-1",
    aws_access_key_id="test",
    aws_secret_access_key="test"
)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith("/data/"):
            key = parsed.path.lstrip("/")

            try:
                response = s3.get_object(
                    Bucket=GENERATED_BUCKET,
                    Key=key
                )
            except ClientError as error:
                code = error.response.get("Error", {}).get("Code")

                if code in {"NoSuchKey", "404"}:
                    self.send_error(404)
                    return

                raise

            body = response["Body"].read()
            content_type = (
                response.get("ContentType")
                or mimetypes.guess_type(key)[0]
                or "application/octet-stream"
            )

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8080), Handler)

    print("CommandLog frontend: http://localhost:8080")
    server.serve_forever()