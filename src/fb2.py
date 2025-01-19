import time
from xml.etree import ElementTree as ET

import requests
from FB2 import FictionBook2
from bs4 import BeautifulSoup

from src.model import ChapterData, ChapterMeta, Handler
from src.api import get_chapter
from src.utils import set_authors


class FB2Handler(Handler):
    book: FictionBook2

    def _parse_html(self, chapter: ChapterData) -> list[ET.Element]:
        try:
            soup = BeautifulSoup(chapter.content, "html.parser")
            tags: list = []
            for tag in soup.find_all(recursive=False):
                tags.append(ET.fromstring(tag.__str__()))
        except Exception as e:
            self.log_func(e)

        return tags

    def _get_tag_name(self, mark_type: str) -> str:
        match mark_type:
            case "bold":
                return "strong"
            case "italic":
                return "emphasis"
            case "underline":
                return "custom"  # В FB2 нет отдельного тега для подчеркивания текста
            case "strike":
                return "strikethrough"
            case _:
                return "custom"

    def _parse_marks(self, marks: list, tag: ET.Element, text: str, index: int = 0) -> ET.Element:
        if index >= len(marks):
            tag.text = text
            return tag

        tag_type = self._get_tag_name(marks[index].get("type"))
        new_tag = ET.Element(tag_type)
        tag.append(self._parse_marks(marks, new_tag, text, index + 1))
        return tag

    def _parse_paragraph(self, paragraph_content: list[dict]) -> ET.Element:
        paragraph: ET.Element = ET.Element("p")
        if not paragraph_content:
            return paragraph

        for element in paragraph_content:
            if element.get("type") == "text":
                ETelement = ET.Element("custom")

                if "marks" in element:
                    self._parse_marks(element.get("marks"), ETelement, element.get("text"))
                else:
                    ETelement.text = element.get("text")

                paragraph.append(ETelement)

        return paragraph

    def _parse_doc(self, chapter: ChapterData) -> list[ET.Element]:
        tags: list = []

        for item in chapter.content:
            item_type = item.get("type")
            match item_type:
                case "paragraph":
                    paragraph = self._parse_doc_content(item.get("content"))
                    tags.append(paragraph)
                case "horizontalRule":
                    tags.append(ET.Element("empty-line"))
                case "heading":
                    level = item.get("attrs").get("level")
                    paragraph_content = item.get("content")
                    if level == 2:
                        tag = ET.Element("title")
                    elif level == 3:
                        tag = ET.Element("subtitle")
                    tag.append(self._parse_paragraph(paragraph_content))
                    tags.append(tag)
        return tags

    def save_book(self, dir: str) -> None:
        save_title = self.book.titleInfo.title.replace(":", "")
        self.book.write(dir + f"\\{save_title}.fb2")
        self.log_func(f"Книга {self.book.titleInfo.title} сохранена в формате FB2!")
        self.log_func(f"В каталоге {dir} создана книга {save_title}.fb2")

    def _make_chapter(self, slug: str, priority_branch: str, item: ChapterMeta) -> list[ET.Element] | None:
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
        worker,
        delay: float = 0.5,
    ) -> None:
        self.min_volume = str(chapters_data[0].volume)
        self.max_volume = str(chapters_data[-1].volume)

        len_total = len(str(len(chapters_data)))
        chap_len = len(str(max(chapters_data, key=lambda x: len(str(x.number))).number))
        volume_len = len(self.max_volume)

        self.log_func(f"Начинаем скачивать главы: {len(chapters_data)}")

        for i, item in enumerate(chapters_data, 1):
            time.sleep(delay)
            if worker.is_cancelled:
                break

            tags: list[ET.Element] | None = self._make_chapter(slug, priority_branch, item)

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
