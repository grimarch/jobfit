"""Logging setup. Call setup() once from cli.py before running any command."""

import inspect
import logging
import sys
from pathlib import Path

from loguru import logger

LOG_DIR = Path("logs")
_FMT = "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name} | {message}"

# ID of the stdout INFO handler — tracked so other code can swap it temporarily.
stdout_handler_id: int | None = None


class _InterceptHandler(logging.Handler):
    """Route Python stdlib logging (uvicorn, sqlalchemy, etc.) through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup(cmd: str) -> None:
    global stdout_handler_id
    logger.remove()

    LOG_DIR.mkdir(exist_ok=True)
    logger.add(
        LOG_DIR / "jobfit.log",
        rotation="1 day",
        retention="14 days",
        compression="gz",
        format=_FMT,
        level="DEBUG",
        encoding="utf-8",
    )

    stdout_handler_id = logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO",
        colorize=True,
        filter=lambda r: r["level"].no < 40,
    )
    logger.add(
        sys.stderr,
        format="<red>{level}</red> | {message}",
        level="ERROR",
        colorize=True,
    )

    intercept_stdlib_logging("openai")
    logger.debug(f"=== jobfit {cmd} ===")


def intercept_stdlib_logging(*logger_names: str) -> None:
    """Redirect stdlib loggers (e.g. uvicorn) into loguru."""
    handler = _InterceptHandler()
    for name in logger_names:
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False
        lg.setLevel(logging.DEBUG)
