from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from logging import root
from typing import Any, Callable, Literal
from xml.etree import ElementTree as ET

from FB2 import FictionBook2
from FB2.FB2Builder import FB2Builder


class MyFB2Builder(FB2Builder):
    def GetFB2(self, root: ET.Element = None) -> ET.Element:
        if root is None:
            root = ET.Element(
                "FictionBook",
                attrib={
                    "xmlns": "http://www.gribuser.ru/xml/fictionbook/2.0",
                    "xmlns:xlink": "http://www.w3.org/1999/xlink",
                },
            )
        self._AddStylesheets(root)
        self._AddCustomInfos(root)
        self._AddDescription(root)
        self._AddBody(root)
        self._AddBinaries(root)
        return root


@dataclass
class MyFictionBook2(FictionBook2):
    root: ET.Element = ET.Element(
        "FictionBook",
        attrib={
            "xmlns": "http://www.gribuser.ru/xml/fictionbook/2.0",
            "xmlns:xlink": "http://www.w3.org/1999/xlink",
        },
    )

    def __str__(self) -> str:
        return FB2Builder._PrettifyXml(MyFB2Builder(self).GetFB2(root=self.root))


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
    def _insert_image(self, image: Image) -> ET.Element:
        pass

    @abstractmethod
    def _get_tag_name(self, mark_type: str) -> ET.Element:
        pass

    @abstractmethod
    def _parse_list(self, *args, **kwargs) -> ET.Element:
        pass

    @abstractmethod
    def _parse_marks(self, marks: list, tag: ET.Element, text: str, index: int = 0) -> ET.Element:
        pass

    @abstractmethod
    def _parse_paragraph(self, paragraph: dict, element: str = "p") -> ET.Element:
        pass

    @abstractmethod
    def _tag_parser(self, tag: dict, **kwargs) -> ET.Element:
        pass

    @abstractmethod
    def _parse_doc(self, chapter: ChapterData) -> list[ET.Element]:
        pass

    @abstractmethod
    def _parse_html(self, chapter: ChapterData) -> list[ET.Element]:
        pass

    @abstractmethod
    def _make_chapter(self, slug: str, priority_branch: str, item: ChapterMeta) -> list[ET.Element]:
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
    def end_book(self) -> None:
        pass

    @abstractmethod
    def save_book(self, dir: str) -> None:
        pass
