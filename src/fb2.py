import base64
import time
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

from src.model import ChapterData, ChapterMeta, Handler, Image, MyFictionBook2
from src.api import get_chapter, get_image_content
from src.utils import set_authors


class FB2Handler(Handler):
    book: MyFictionBook2

    def _parse_html(self, chapter: ChapterData) -> list[ET.Element]:
        try:
            soup = BeautifulSoup(chapter.content, "html.parser")
            tags: list = []
            for tag in soup.find_all(recursive=False):
                tags.append(ET.fromstring(tag.__str__()))
        except Exception as e:
            self.log_func(e)

        return tags

    def _get_tag_name(self, mark_type: str) -> ET.Element:
        match mark_type:
            case "bold":
                return ET.Element("strong")
            case "italic":
                return ET.Element("emphasis")
            case "underline":
                return ET.Element("style", attrib={"name": "underline"})
            case "strike":
                return ET.Element("strikethrough")
            case _:
                return ET.Element("custom")

    def _parse_marks(self, marks: list, tag: ET.Element, text: str, index: int = 0) -> ET.Element:
        if index >= len(marks):
            tag.text = text
            return tag

        new_tag = self._get_tag_name(marks[index].get("type"))
        tag.append(self._parse_marks(marks, new_tag, text, index + 1))
        return tag

    def _parse_paragraph(self, paragraph: dict, element: str = "p") -> ET.Element:
        paragraphE: ET.Element = ET.Element(element)

        attrs = paragraph.get("attrs")
        if attrs:
            aling = attrs.get("textAlign")
            paragraphE.attrib["align"] = aling or "left"

        if "content" not in paragraph:
            return paragraphE

        for element in paragraph.get("content"):
            if element.get("type") == "text":
                ETelement = ET.Element("custom")

                if "marks" in element:
                    self._parse_marks(element.get("marks"), ETelement, element.get("text"))
                else:
                    ETelement.text = element.get("text")

                paragraphE.append(ETelement)

        return paragraphE

    def _parse_list(self, list_obj: dict, list_type: str, level=1) -> ET.Element:
        listE: ET.Element = ET.Element("custom")
        for i, list_item in enumerate(list_obj, start=1):
            if "content" not in list_item:
                continue

            prefix = " " * (level * 2) + f"{i}. " if list_type == "orderedList" else "• "

            for element in list_item.get("content"):
                tag = self._tag_parser(element, level=level + 1)

                if tag.tag == "p":
                    tag.text = prefix + (tag.text or "")

                listE.append(tag)

        return listE

    def _tag_parser(self, tag: dict, **kwargs) -> ET.Element:
        item_type = tag.get("type")
        match item_type:
            case "image":
                img_name = tag.get("attrs").get("images")[-1].get("image")
                img_obj: Image = self.images.get(img_name)
                binaryE = ET.Element(
                    "binary",
                    attrib={
                        "id": img_obj.uid,
                        "content-type": img_obj.media_type,
                    },
                )
                binaryE.text = base64.b64encode(get_image_content(img_obj.url, img_obj.extension)).decode("utf-8")
                self.book.root.append(binaryE)

                return ET.Element("image", attrib={"xlink:href": f"#{img_obj.uid}"})

            case "paragraph":
                return self._parse_paragraph(tag)

            case "horizontalRule":
                return ET.Element("empty-line")

            case "bulletList" | "orderedList":
                list_items = tag.get("content")
                return self._parse_list(list_items, item_type, **kwargs)

            case "heading":
                level = tag.get("attrs").get("level")
                return self._parse_paragraph(tag, "title" if level == 2 else "subtitle")

            case "blockquote":
                blockquoteE = ET.Element("epigraph")
                for b_tag in tag.get("content"):
                    blockquoteE.append(self._tag_parser(b_tag))
                return blockquoteE

    def _parse_doc(self, chapter: ChapterData) -> list[ET.Element]:
        attachments = chapter.attachments
        img_base_url = "https://ranobelib.me"
        images: dict[str, Image] = {}
        tags: list[ET.Element] = []

        for attachment in attachments:
            img_uid = f"{chapter.id}_{attachment.filename}"
            images[attachment.name] = Image(
                uid=img_uid,
                name=attachment.name,
                url=img_base_url + attachment.url,
                extension=attachment.extension,
            )
            self.images = images

        for item in chapter.content:
            tag = self._tag_parser(item)
            tags.append(tag)

        return tags, images

    def save_book(self, dir: str) -> None:
        save_title = self.book.titleInfo.title.replace(":", "")
        self.book.write(dir + f"\\{1}.fb2")
        self.log_func(f"Книга {self.book.titleInfo.title} сохранена в формате FB2!")
        self.log_func(f"В каталоге {dir} создана книга {save_title}.fb2")

    def end_book(self) -> None:
        self.book.titleInfo.sequences = [
            (
                self.book.titleInfo.title,
                f"Тома c {self.min_volume} по {self.max_volume}",
            )
        ]

    def _make_chapter(
        self, slug: str, priority_branch: str, item: ChapterMeta
    ) -> tuple[list[ET.Element], dict[str, Image]]:
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
            tags, images = self._parse_doc(chapter)

        else:
            self.log_func("Неизвестный тип главы! Невозможно преобразовать в FB2!")

        return tags, images

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

            tags, images = self._make_chapter(slug, priority_branch, item)

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
        book = MyFictionBook2()
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
