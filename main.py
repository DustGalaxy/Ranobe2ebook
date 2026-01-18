import logging
from pathlib import Path
from typing import Dict

from src.model import Handler
from src.menu import Ranobe2ebook
from src.fb2 import FB2Handler
from src.epub import EpubHandler
from src.config import config

def setup_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=logs_dir / "ranobe2ebook.log",
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_handlers() -> Dict[str, Handler]:
    """Возвращает словарь доступных обработчиков форматов."""
    return {"fb2": FB2Handler, "epub": EpubHandler}


def main() -> None:
    docs_path = Path.home() / "Documents"
    if not (docs_path / "ranobelib-parser-logs").exists():
        (docs_path / "ranobelib-parser-logs").mkdir(parents=True)

    logs_dir = docs_path / "ranobelib-parser-logs"
    if not logs_dir.exists():
        logs_dir.mkdir(parents=True)
    
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
        logger.exception("Произошла непредвиденная ошибка")
        print(f"Произошла непредвиденная ошибка.\nПодробности в файле: {logs_dir}/app.log")
        input("Нажмите Enter для выхода...")


if __name__ == "__main__":
    main()
