from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class SPAStaticHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        translated = Path(super().translate_path(path))
        if translated.exists():
            return str(translated)
        return str(Path.cwd() / "index.html")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 5173), SPAStaticHandler)
    print("Serving SPA preview at http://127.0.0.1:5173", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
