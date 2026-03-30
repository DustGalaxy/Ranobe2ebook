import json
import logging
import shutil
from pathlib import Path

from src.model import ChapterData, Attachment
from src.utils import sanitize_path_component
from src.config import config


logger = logging.getLogger(__name__)


def clear_cache():
    if config.cache_dir and config.cache_dir.exists():
        for path in config.cache_dir.iterdir():
            try:
                if path.is_file() or path.is_symlink():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
            except Exception as e:
                logger.error(f"Error deleting cache path {path}: {e}")


def get_cache_path(ranobe_name: str, priority_branch: str, number: int, volume: int) -> Path:
    """Возвращает путь к кеш-файлу для главы."""
    path = (
        config.cache_dir / sanitize_path_component(ranobe_name) / sanitize_path_component(priority_branch) / str(volume)
    )
    path.mkdir(parents=True, exist_ok=True)
    filename = f"{number}.json"
    return path / filename


def cache_chapter(cache_path: Path, chapter: ChapterData, attachments: list[Attachment]):
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "id": chapter.id,
                "number": chapter.number,
                "volume": chapter.volume,
                "type": chapter.type,
                "content": chapter.content,
                "attachments": [a.__dict__ for a in attachments],
            },
            f,
            ensure_ascii=False,
            indent=4,
        )
