"""Run the API: ``python -m app.api.server`` (from the backend folder)."""

from __future__ import annotations

import uvicorn

from app.api.main import create_app
from app.core.config import Settings, configure_logging


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
