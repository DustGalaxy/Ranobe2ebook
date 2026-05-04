import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict

docs_path = Path.home() / "Documents"
if not (docs_path / "ranobelib-parser-logs").exists():
    (docs_path / "ranobelib-parser-logs").mkdir(parents=True)


logs_dir = docs_path / "ranobelib-parser-logs"


def setup_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = os.path.join(logs_dir, "ranobe2ebook.log")
    os.makedirs(logs_dir, exist_ok=True)

    max_size = 2 * 1024 * 1024
    backups = 4

    handler = RotatingFileHandler(log_file, maxBytes=max_size, backupCount=backups, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(funcName)s:%(lineno)d - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[handler],
    )


setup_logging(logs_dir)

from src.model import Handler
from src.menu import Ranobe2ebook
from src.fb2 import FB2Handler
from src.epub import EpubHandler
from src.config import config


def get_handlers() -> Dict[str, type[Handler]]:
    """Возвращает словарь доступных обработчиков форматов."""
    return {"fb2": FB2Handler, "epub": EpubHandler}


def main() -> None:

    if not (docs_path / "ranobelib-parser-cache").exists():
        (docs_path / "ranobelib-parser-cache").mkdir(parents=True)

    cache_path = docs_path / "ranobelib-parser-cache"

    config.cache_dir = cache_path

    setup_logging(logs_dir)
    logger = logging.getLogger(__name__)

    try:
        app = Ranobe2ebook(handlers=get_handlers())
        app.run()
    except Exception as e:
        logger.exception("An unexpected error occurred in the main application loop.")
        print(f"Произошла непредвиденная ошибка.\nПодробности в файле: {logs_dir}/app.log")
        input("Нажмите Enter для выхода...")
    finally:
        for handler in logging.getLogger().handlers:
            handler.flush()
            handler.close()


if __name__ == "__main__":
    main()
