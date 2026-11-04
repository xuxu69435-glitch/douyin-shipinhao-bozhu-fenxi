"""PyInstaller entry point. Tauri controls port, auth token and data directory."""

import uvicorn

from app.config import Settings
from app.main import create_app


def main():
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(settings.data_dir, settings.backend_token)
    uvicorn.run(app, host="127.0.0.1", port=settings.backend_port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
