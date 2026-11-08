"""Optional native AEGIS application window; browser fallback needs no extra package."""

from threading import Thread
from app import AegisHandler, HOST, PORT, ThreadingHTTPServer, run_server, STORE


def main():
    try:
        import webview
    except ImportError:
        print("AEGIS native window support is optional (pywebview not installed).")
        print("Opening the local application in your browser instead.")
        run_server(open_browser=True)
        return

    server = ThreadingHTTPServer((HOST, PORT), AegisHandler)
    worker = Thread(target=server.serve_forever, kwargs={"poll_interval": .2}, daemon=True)
    worker.start()
    print("AEGIS — LOCAL DESKTOP APPLICATION")
    print("Research export:", "VERIFIED" if STORE.ready else "SETUP REQUIRED")
    print("Operational execution: DISABLED")
    try:
        webview.create_window(
            "AEGIS — Research Intelligence", f"http://{HOST}:{PORT}/",
            width=1500, height=920, min_size=(980, 660),
            background_color="#07101f",
        )
        webview.start()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


if __name__ == "__main__":
    main()
