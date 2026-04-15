import logging
from flask import Flask


def configure_logging(app: Flask) -> None:
    """Configure root logger — all module loggers inherit this automatically."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    app.logger.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Formatting is set by configure_logging at startup."""
    return logging.getLogger(name)
