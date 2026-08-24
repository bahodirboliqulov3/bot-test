import os
import sys
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Telegram Test Platform Bot is LIVE 24/7!")

    def log_message(self, format, *args):
        pass

def start_http_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        print(f"Health check HTTP server listening on 0.0.0.0:{port}")
        server.serve_forever()
    except Exception as e:
        print(f"HTTP Server note: {e}")

if __name__ == "__main__":
    # 1. Start HTTP health server in background thread for Render/Koyeb/Cloud
    t = threading.Thread(target=start_http_server, daemon=True)
    t.start()

    # 2. Run Telegram Bot in main thread
    from app.main import main
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot process terminated gracefully.")
    except Exception as e:
        import traceback
        print(f"Bot error: {e}")
        traceback.print_exc()
        sys.exit(1)
