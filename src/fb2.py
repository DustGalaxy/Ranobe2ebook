import os
import re
import time
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from FB2 import FictionBook2dataclass
from FB2.FB2Builder import FB2Builder
from bs4 import BeautifulSoup

from src.model import ChapterData, ChapterMeta, Handler, Image
from src.api import get_chapter, get_image_content
from src.utils import set_authors


@dataclass
class MyFictionBook2dataclass(FictionBook2dataclass.FictionBook2dataclass):
    images: list[Image] = field(default_factory=list)


class MyFB2Builder(FB2Builder):
    book: MyFictionBook2dataclass

    def _AddBody(self, root: ET.Element) -> None:
        if len(self.book.chapters):
            bodyElement = ET.SubElement(root, "body")
            for chapter in self.book.chapters:
                bodyElement.append(self.BuildSectionFromChapter(chapter))

    def _AddBinaries(self, root: ET.Element) -> None:
        if self.book.titleInfo.coverPageImages is not None:
            for i, coverImage in enumerate(self.book.titleInfo.coverPageImages):
                self._AddBinary(root, f"title-info-cover_{i}", "image/jpeg", coverImage)
        if self.book.sourceTitleInfo and self.book.sourceTitleInfo.coverPageImages:
            for i, coverImage in enumerate(self.book.sourceTitleInfo.coverPageImages):
                self._AddBinary(root, f"src-title-info-cover#{i}", "image/jpeg", coverImage)
        if len(self.book.images) > 0:
            for image in self.book.images:
                self._AddBinary(root, image.uid, image.media_type, image.content)


@dataclass
class MyFictionBook2(MyFictionBook2dataclass):
    def write(self, filename: str):
        with open(filename, "w", encoding="utf-8") as f:
            f.write(str(self))

    def __str__(self) -> str:
        return MyFB2Builder._PrettifyXml(MyFB2Builder(self).GetFB2())


class FB2Handler(Handler):
    book: MyFictionBook2
    style_tags = {
        "bold": ET.Element("strong"),
        "italic": ET.Element("emphasis"),
        "underline": ET.Element("style", attrib={"name": "underline"}),
        "strike": ET.Element("strikethrough"),
    }

    def _parse_html(self, chapter: ChapterData) -> list[ET.Element]:
        soup = BeautifulSoup(chapter.content, "html.parser")
        tags: list[ET.Element] = []
        for tag in soup.find_all(recursive=False):
            if tag.name == "p":
                tag.attrs.pop("data-paragraph-index")
            if tag.name == "img":
                url = tag["src"]
                img_filename = url.split("/")[-1]
                img_uid = f"{chapter.id}_{img_filename}"
                try:
                    content = get_image_content(url, img_filename.split(".")[-1])
                    image = Image(
                        uid=img_uid,
                        extension=img_filename.split(".")[-1],
                        content=content,
                    )
                    imageE = self._insert_image(image) if self.with_images else ET.Element("custom")
                    tags.append(imageE)
                except Exception as e:
                    self.log_func("Ошибка: " + str(e))
                continue
            tags.append(ET.fromstring(str(tag)))

        return tags

    def _insert_image(self, image: Image) -> ET.Element:
        for img in self.book.images:
            if img.content == image.content:
                return ET.Element("image", attrib={"{http://www.w3.org/1999/xlink}href": f"#{img.uid}"})

        self.book.images.append(image)
        return ET.Element("image", attrib={"{http://www.w3.org/1999/xlink}href": f"#{image.uid}"})

    def _parse_marks(self, marks: list, tag: ET.Element, text: str, _index: int = 0) -> ET.Element:
        if _index >= len(marks):
            tag.text = text
            return tag

        new_tag = self.style_tags.get(marks[_index].get("type"), ET.Element("span"))
        tag.append(self._parse_marks(marks, new_tag, text, _index + 1))
        return tag

    def _parse_paragraph(self, paragraph: dict, element: str = "p") -> ET.Element:
        paragraphE = ET.Element(element)

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

    def _parse_list(self, list_obj: dict, type: str, level=1) -> ET.Element:
        listE: ET.Element = ET.Element("custom")
        for i, list_item in enumerate(list_obj, start=1):
            if "content" not in list_item:
                continue

            prefix = " " * (level * 2) + f"{i}. " if type == "orderedList" else "• "

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
                images: dict[str, Image] = kwargs.get("images")
                if not images:
                    return ET.Element("custom")
                img_name = tag.get("attrs").get("images")[-1].get("image")
                img = images.get(img_name)
                return self._insert_image(img) if img and self.with_images else ET.Element("custom")

            case "paragraph":
                return self._parse_paragraph(tag)

            case "horizontalRule":
                center = {"style": "text-align: center"}
                hr = ET.Element("p", attrib=center)
                hr.text = "* * *"
                return hr

            case "bulletList" | "orderedList":
                list_items = tag.get("content")
                return self._parse_list(list_items, item_type, kwargs.get("level", 1))

            case "heading":
                level = tag.get("attrs").get("level")
                el_type = "title" if level == 2 else "subtitle"
                heading = ET.Element(el_type)
                heading.append(self._parse_paragraph(tag))
                return heading

            case "blockquote":
                blockquoteE = ET.Element("epigraph")
                for b_tag in tag.get("content"):
                    blockquoteE.append(self._tag_parser(b_tag, kwargs=kwargs))
                return blockquoteE

    def _parse_doc(self, chapter: ChapterData) -> list[ET.Element]:
        attachments = chapter.attachments
        img_base_url = "https://ranobelib.me"
        images: dict[str, Image] = {}

        for attachment in attachments:
            img_uid = f"{chapter.id}_{attachment.filename}"
            try:
                content = get_image_content(img_base_url + attachment.url, attachment.extension)
            except Exception as e:
                self.log_func("Ошибка: " + str(e))
                continue

            images[attachment.name] = Image(
                uid=img_uid,
                extension=attachment.extension,
                content=content,
            )

        tags: list[ET.Element] = []
        for item in chapter.content:
            tag: ET.Element = self._tag_parser(item, images=images)
            tags.append(tag)
        return tags

    def _make_chapter(
        self, slug: str, priority_branch: str, chapter_meta: ChapterMeta
    ) -> tuple[str, list[ET.Element]] | None:
        try:
            chapter: ChapterData = get_chapter(
                slug,
                priority_branch,
                chapter_meta.number,
                chapter_meta.volume,
            )
        except Exception as e:
            self.log_func("Ошибка: " + str(e))
            return None

        tags: list[ET.Element] = None

        if chapter.type == "html":
            tags = self._parse_html(chapter)
        elif chapter.type == "doc":
            tags = self._parse_doc(chapter)
        else:
            self.log_func("Неизвестный тип главы! Невозможно преобразовать в FB2!")
            return None

        clean_tags: list[str] = []
        for element in tags:
            text_tag = ET.tostring(element)
            soup = BeautifulSoup(text_tag, "html.parser")
            for custom in soup.find_all("custom"):
                custom.unwrap()
            clean_tags.append(str(soup))

        clean_elements = [ET.fromstring(tag) for tag in clean_tags]

        chapter_title = f"Том {chapter_meta.volume}. Глава {chapter_meta.number}. {chapter_meta.name}"
        return (chapter_title, clean_elements)

    def fill_book(
        self,
        slug: str,
        priority_branch: str,
        chapters_data: list[ChapterMeta],
        worker,
        delay: float = 0.5,
    ) -> None:
        self.max_chapter = str(chapters_data[-1].number)
        self.min_chapter = str(chapters_data[0].number)

        len_total = len(str(len(chapters_data)))
        chap_len = len(str(max(chapters_data, key=lambda x: len(str(x.number))).number))
        volume_len = len(str(chapters_data[-1].volume))

        self.log_func(f"Начинаем скачивать главы: {len(chapters_data)}")

        for i, chapter_meta in enumerate(chapters_data, 1):
            time.sleep(delay)
            if worker.is_cancelled:
                break

            chapter = self._make_chapter(slug, priority_branch, chapter_meta)

            if chapter:
                self.book.chapters.append(chapter)

                self.log_func(
                    f"Скачали {i:>{len_total}}: Том {chapter_meta.volume:>{volume_len}}. Глава {chapter_meta.number:>{chap_len}}. {chapter_meta.name}"
                )
            else:
                self.log_func("Пропускаем главу.")

            self.progress_bar_step(1)

    def save_book(self, dir: str) -> None:
        safe_title = re.sub(r'[<>:"/\\|?*]', "", self.book.titleInfo.title)
        file_path = os.path.join(dir, f"{safe_title}.fb2")
        self.book.write(file_path)
        self.log_func(f"Книга {self.book.titleInfo.title} сохранена в формате FB2!")
        self.log_func(f"В каталоге {dir} создана книга {safe_title}.fb2")
        self.book = None

    def end_book(self) -> None:
        self.book.titleInfo.sequences = [
            (
                self.book.titleInfo.title,
                f"Главы c {self.min_chapter} по {self.max_chapter}",
            )
        ]

    def make_book(self, ranobe_data: dict) -> None:
        self.log_func("Подготавливаем книгу...")

        title = ranobe_data.get("rus_name") if ranobe_data.get("rus_name") else ranobe_data.get("name")
        book = MyFictionBook2()
        book.titleInfo.title = title
        book.titleInfo.annotation = ranobe_data.get("summary")
        book.titleInfo.authors = set_authors(ranobe_data.get("authors"))
        book.titleInfo.genres = [genre.get("name") for genre in ranobe_data.get("genres")]
        book.titleInfo.lang = "ru"
        book.documentInfo.programUsed = "Ranobe2ebook"
        book.customInfos = ["meta", "rating"]
        cover_url = ranobe_data.get("cover").get("default")
        book.titleInfo.coverPageImages = [get_image_content(cover_url, cover_url.split(".")[-1])]

        self.log_func("Подготовили книгу.")
        self.book = book
