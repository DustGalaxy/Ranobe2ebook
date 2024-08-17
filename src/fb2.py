import time
from typing import Callable
from xml.etree import ElementTree as ET

import requests
from FB2 import FictionBook2
from bs4 import BeautifulSoup

from src.model import ChapterData, ChapterMeta, Handler
from src.api import get_chapter
from src.utils import set_authors


class FB2Handler(Handler):
    book: FictionBook2
    log_func: Callable
    progress_bar_step: Callable
    min_volume: str
    max_volume: str

    def _parse_html(self, chapter: ChapterData) -> list[ET.Element]:
        try:
            soup = BeautifulSoup(chapter.content, "html.parser")
            tags: list = []
            for tag in soup.find_all(True):
                tags.append(ET.fromstring(tag.__str__()))
        except Exception as e:
            self.log_func(e)

        return tags

    def _parse_doc(self, chapter: ChapterData) -> list[ET.Element]:
        tags: list = []

        for item in chapter.content:
            if item.get("type") == "image":
                pass

            elif item.get("type") == "paragraph":
                text = ""
                paragraph_content = item.get("content")
                if paragraph_content and paragraph_content[0].get("type") == "text":
                    text = paragraph_content[0].get("text")
                tag = ET.Element("p")
                tag.text = text
                tags.append(tag)

            elif item.get("type") == "horizontalRule":
                tags.append(ET.Element("hr"))

        return tags

    def save_book(self, dir: str) -> None:
        save_title = self.book.titleInfo.title.replace(":", "")
        self.book.write(dir + f"\\{save_title}.fb2")
        self.log_func(f"Книга {self.book.titleInfo.title} сохранена в формате FB2!")
        self.log_func(f"В каталоге {dir} создана книга {save_title}.fb2")

    def _make_chapter(
        self, slug: str, priority_branch: str, item: ChapterMeta, delay: float
    ) -> list[ET.Element] | None:
        time.sleep(delay)
        try:
            chapter: ChapterData = get_chapter(
                slug,
                priority_branch,
                item.number,
                item.volume,
            )
        except Exception as e:
            self.log_func(str(e))
            return None

        if chapter.type == "html":
            tags = self._parse_html(chapter)
        elif chapter.type == "doc":
            tags = self._parse_doc(chapter)

        else:
            self.log_func("Неизвестный тип главы! Невозможно преобразовать в FB2!")

        return tags

    def end_book(self) -> None:
        self.book.titleInfo.sequences = [
            (
                self.book.titleInfo.title,
                f"Тома c {self.min_volume} по {self.max_volume}",
            )
        ]

    def fill_book(
        self,
        slug: str,
        priority_branch: str,
        chapters_data: list[ChapterMeta],
        delay: float = 0.5,
    ) -> None:
        self.min_volume = str(chapters_data[0].volume)
        self.max_volume = str(chapters_data[-1].volume)

        len_total = len(str(len(chapters_data)))
        chap_len = len(str(max(chapters_data, key=lambda x: len(str(x.number))).number))
        volume_len = len(self.max_volume)

        self.log_func(f"Начинаем скачивать главы: {len(chapters_data)}")

        for i, item in enumerate(chapters_data, 1):
            tags: list[ET.Element] | None = self._make_chapter(slug, priority_branch, item, delay)

            if tags is None:
                self.log_func("Пропускаем главу.")
                continue

            chap_title = f"Том {item.volume}. Глава {item.number}. {item.name}"

            self.book.chapters.append(
                (
                    chap_title,
                    [tag for tag in tags],
                )
            )

            self.log_func(
                f"Скачали {i:>{len_total}}: Том {item.volume:>{volume_len}}. Глава {item.number:>{chap_len}}. {item.name}"
            )

            self.progress_bar_step(1)

    def make_book(self, ranobe_data: dict) -> None:
        self.log_func("Подготавливаем книгу...")

        title = ranobe_data.get("rus_name") if ranobe_data.get("rus_name") else ranobe_data.get("name")
        book = FictionBook2()
        book.titleInfo.title = title
        book.titleInfo.annotation = ranobe_data.get("summary")
        book.titleInfo.authors = set_authors(ranobe_data.get("authors"))
        book.titleInfo.genres = [genre.get("name") for genre in ranobe_data.get("genres")]
        book.titleInfo.lang = "ru"
        book.documentInfo.programUsed = "RanobeLIB 2 ebook"
        book.customInfos = ["meta", "rating"]
        book.titleInfo.coverPageImages = [requests.get(ranobe_data.get("cover").get("default")).content]

        self.log_func("Подготовили книгу.")
        self.book = book
