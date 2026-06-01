import logging
import os


LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(source)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class SourceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "source"):
            record.source = "app"
        return True


class LinePrefixFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        lines = text.splitlines()
        if len(lines) <= 1:
            return text

        prefix = (
            f"{self.formatTime(record, self.datefmt)} "
            f"[{record.levelname}] [{getattr(record, 'source', 'app')}] "
        )
        return "\n".join([lines[0], *[prefix + line for line in lines[1:]]])


def configure_logging(log_path: str) -> logging.Logger:
    logger = logging.getLogger("savemedia")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    abs_path = os.path.abspath(log_path)
    for handler in list(logger.handlers):
        if getattr(handler, "baseFilename", None) == abs_path:
            return logger
        logger.removeHandler(handler)
        handler.close()

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    handler = logging.FileHandler(abs_path, encoding="utf-8")
    handler.addFilter(SourceFilter())
    handler.setFormatter(LinePrefixFormatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger.addHandler(handler)
    return logger


def get_logger(source: str = "app") -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logging.getLogger("savemedia"), {"source": source})
