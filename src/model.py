from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


@dataclass
class State:
    is_data_loaded: bool = False
    is_branch_selected: bool = False
    is_chapters_selected: bool = False
    is_dir_selected: bool = False


@dataclass
class Image:
    uid: str
    name: str
    url: str
    extension: str
    static_url: str = ""
    media_type: str = ""

    def __post_init__(self) -> None:
        self.static_url = f"static/{self.uid}"
        self.media_type = f"image/{self.extension}"


@dataclass
class ChapterMeta:
    name: str
    number: int
    volume: int


@dataclass
class Attachment:
    id: str | None
    filename: str
    name: str
    extension: Literal["png", "jpg", "jpeg", "gif"]
    url: str
    width: int
    height: int


@dataclass
class ChapterData:
    id: str
    number: int
    volume: int
    type: Literal["doc", "html"]
    content: list[dict]
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class Exception:
    message: str


@dataclass
class Config:
    token: str = ""


class Handler(ABC):
    log_func: Callable
    progress_bar_step: Callable
    min_volume: str
    max_volume: str

    def __init__(self, log_func: Callable, progress_bar_step: Callable) -> None:
        self.log_func = log_func
        self.progress_bar_step = progress_bar_step

    @abstractmethod
    def _get_tag_name(self, mark_type: str) -> str:
        pass

    @abstractmethod
    def _parse_list(self, *args, **kwargs) -> Any:
        pass

    @abstractmethod
    def _parse_marks(self, *args, **kwargs) -> Any:
        pass

    @abstractmethod
    def _parse_paragraph(self, paragraph_content: list[dict]) -> Any:
        pass

    @abstractmethod
    def fill_book(
        self, slug: str, priority_branch: str, chapters_data: list[ChapterMeta], worker, delay: float = 0.5
    ) -> None:
        pass

    @abstractmethod
    def make_book(self, ranobe_data: dict) -> None:
        pass

    @abstractmethod
    def _make_chapter(self, slug: str, priority_branch: str, item: ChapterMeta) -> Any:
        pass

    @abstractmethod
    def end_book(self) -> None:
        pass

    @abstractmethod
    def save_book(self, dir: str) -> None:
        pass
