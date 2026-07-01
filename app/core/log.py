import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from app.conf.app_config import config


def setup_logging(name: str = "agentic-rag", level: Optional[str] = None) -> logging.Logger:
    log_level = level or config.LOG_LEVEL
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)

    # 文件输出：自动轮转，单文件 10MB，保留 5 份；受限环境不可写时降级为控制台日志。
    try:
        log_dir = Path(config.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{name}.log"
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=config.LOG_FILE_MAX_BYTES,
            backupCount=config.LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("File logging disabled: %s", exc)

    logger.propagate = False

    return logger


logger = setup_logging()
