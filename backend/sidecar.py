"""PyInstaller entry point. Tauri controls port, auth token and data directory."""

import os
import sys


def main():
    if "--collection-probe" in sys.argv:
        from app.collection_probe import probe_main
        return probe_main()
    import uvicorn
    from app.config import Settings
    from app.main import create_app
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(settings.data_dir, settings.backend_token,
                     enable_live=os.getenv("ANALYST_ENABLE_LIVE") == "1")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=settings.backend_port,
                                         workers=1, access_log=False, timeout_graceful_shutdown=2))
    app.state.request_shutdown = lambda: setattr(server, "should_exit", True)
    server.run()


if __name__ == "__main__":
    main()
