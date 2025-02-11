import time
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from ebooklib import epub
import requests

from src.model import ChapterData, ChapterMeta, Image, Handler
from src.api import get_chapter, get_image_content


class EpubHandler(Handler):
    book: epub.EpubBook
    images: dict[str, Image]

    def _parse_html(self, chapter: ChapterData) -> tuple[list[str], dict[str, Image]]:
        try:
            soup = BeautifulSoup(chapter.content, "html.parser")
            tags: list = []
            images: dict[str, Image] = {}
            for tag in soup.find_all(recursive=False):
                if tag.name == "img":
                    url = tag["src"]
                    img_filename = url.split("/")[-1]
                    img_uid = f"{chapter.id}_{img_filename}"
                    image = Image(
                        uid=img_uid,
                        name=img_filename.split(".")[0],
                        url=url,
                        extension=img_filename.split(".")[-1],
                    )
                    images[image.name] = image
                    tag["src"] = image.static_url

                tags.append(tag)
        except Exception as e:
            self.log_func(e)

        return tags, images

    def _get_tag_name(self, mark_type: str) -> ET.Element:
        match mark_type:
            case "bold":
                return ET.Element("b")
            case "italic":
                return ET.Element("i")
            case "underline":
                return ET.Element("ins")
            case "strike":
                return ET.Element("del")
            case _:
                return ET.Element("span")

    # def _parse_marks(self, marks: list[str], text: str) -> str:
    #     pre_tag: list[str] = []
    #     post_tag: list[str] = []
    #     for mark in marks:
    #         tag = self._get_tag_name(mark.get("type"))
    #         pre_tag.append(f"<{tag}>")
    #         post_tag.append(f"</{tag}>")

    #     return text if len(pre_tag) == 0 else "".join(pre_tag) + text + "".join(post_tag[::-1])

    # def _parse_text(self, text_tag: str) -> str:
    #     text = ""
    #     for element in text_tag:
    #         if element.get("type") == "text":
    #             if "marks" in element:
    #                 text += self._parse_marks(element.get("marks"), element.get("text"))
    #             else:
    #                 text += "<span>" + element.get("text") + "</span>"
    #     self.log_func(text)
    #     return ET.fromstring(text)

    # def _parse_paragraph(self, paragraph: dict, element: str = "p") -> ET.Element:
    #     paragraphE = ET.Element(element)

    #     if not paragraph.get("content"):
    #         return paragraphE

    #     attrs = paragraph.get("attrs")
    #     if attrs:
    #         aling = attrs.get("textAlign")
    #         paragraphE.attrib["style"] = f"text-align: {aling};"
    #     text = self._parse_text(paragraph.get("content"))
    #     paragraphE.append(text)

    #     return paragraphE

    def _parse_marks(self, marks: list, tag: ET.Element, text: str, index: int = 0) -> ET.Element:
        if index >= len(marks):
            tag.text = text
            return tag

        new_tag = self._get_tag_name(marks[index].get("type"))
        tag.append(self._parse_marks(marks, new_tag, text, index + 1))
        return tag

    def _parse_paragraph(self, paragraph: dict, element: str = "p") -> ET.Element:
        paragraphE = ET.Element(element)

        if not paragraph.get("content"):
            return paragraphE

        attrs = paragraph.get("attrs")
        if attrs:
            aling = attrs.get("textAlign")
            paragraphE.attrib["style"] = f"text-align: {aling or 'left'};"

        for element in paragraph.get("content"):
            if element.get("type") == "text":
                ETelement = ET.Element("span")

                if "marks" in element:
                    self._parse_marks(element.get("marks"), ETelement, element.get("text"))
                else:
                    ETelement.text = element.get("text")

                paragraphE.append(ETelement)

        return paragraphE

    def _parse_list(self, list_content: list[dict], type: str) -> ET.Element:
        listE = ET.Element("ul" if type == "bulletList" else "ol")
        for list_item in list_content:
            li = ET.SubElement(listE, "li")

            for li_content in list_item.get("content"):
                tag = self._tag_parser(li_content)
                li.append(tag)

        return listE

    def _tag_parser(self, tag: dict) -> ET.Element:
        tag_type = tag.get("type")
        match tag_type:
            case "image":
                img_name = tag.get("attrs").get("images")[-1].get("image")
                return ET.Element("img", attrib={"src": f"static/{self.images.get(img_name).uid}"})

            case "paragraph":
                return self._parse_paragraph(tag)

            case "horizontalRule":
                return ET.Element("hr", attrib={"style": "width: 100%;"})

            case "bulletList" | "orderedList":
                list_items = tag.get("content")
                listE = self._parse_list(list_items, tag_type)
                self.log_func(str(listE))
                return listE

            case "heading":
                level = tag.get("attrs").get("level")
                return self._parse_paragraph(tag, "h" + str(level))

            case "blockquote":
                blockquoteE = ET.Element(
                    "blockquote",
                    attrib={"style": "background-color: rgba(0, 0, 0, 0.2); padding: 10px 20px; border-radius: 15px;"},
                )
                for b_tag in tag.get("content"):
                    blockquoteE.append(self._tag_parser(b_tag))
                return blockquoteE

    def _parse_doc(self, chapter: ChapterData) -> tuple[list[ET.Element], dict[str, Image]]:
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
            tmp = self._tag_parser(item)
            tags.append(tmp)

        return tags, images

    def _make_chapter(
        self, slug: str, priority_branch: str, item: ChapterMeta
    ) -> tuple[epub.EpubHtml, dict[str, Image]]:
        try:
            chapter: ChapterData = get_chapter(
                slug,
                priority_branch,
                item.number,
                item.volume,
            )
        except Exception as e:
            self.log_func(str(e))
            return None, None

        chapter_title = f"Том {item.volume}. Глава {item.number}. {item.name}"

        epub_chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=item.number + "_" + item.volume + ".xhtml",
        )
        tags, images = [], {}

        if chapter.type == "html":
            tags, images = self._parse_html(chapter)
            epub_chapter.set_content(f"<h1>{chapter_title}</h1>" + "".join([tag.__str__() for tag in tags]))

        elif chapter.type == "doc":
            tags, images = self._parse_doc(chapter)
            for tag in tags:
                self.log_func(str(tag))
            epub_chapter.set_content(
                f"<h1>{chapter_title}</h1>"
                + "".join([ET.tostring(tag, encoding="unicode", method="html") for tag in tags]),
            )
        else:
            self.log_func("Неизвестный тип главы! Невозможно преобразовать в EPUB!")
            return None, None

        return epub_chapter, images

    def save_book(self, dir: str) -> None:
        safe_title = self.book.title.replace(":", "")
        epub.write_epub(f"{dir}\\{safe_title}.epub", self.book)
        self.log_func(f"Книга {self.book.title} сохранена в формате Epub.")
        self.log_func(f"В каталоге {dir} создана книга {safe_title}.epub.")

    def end_book(self) -> None:
        self.book.toc = (epub.Section("1"),) + tuple(
            chap for chap in self.book.items if isinstance(chap, epub.EpubHtml)
        )

        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())
        self.book.spine = [chap for chap in self.book.items if isinstance(chap, epub.EpubHtml)]
        self.book.spine = [self.book.spine[-1]] + self.book.spine[:-1]

        self.book.add_metadata(
            None,
            "meta",
            "",
            {"name": "series_index", "content": f"Тома c {self.min_volume} по {self.max_volume}"},
        )

    def fill_book(
        self,
        name: str,
        priority_branch: str,
        chapters_data: list[ChapterMeta],
        worker,
        delay: float = 0.5,
    ) -> None:
        self.min_volume = str(chapters_data[0].volume)
        self.max_volume = str(chapters_data[-1].volume)

        total_len = len(str(len(chapters_data)))
        chap_len = len(str(max(chapters_data, key=lambda x: len(str(x.number))).number))
        volume_len = len(self.max_volume)

        self.log_func(f"\nНачинаем скачивать главы: {len(chapters_data)}")

        for i, item in enumerate(chapters_data, 1):
            time.sleep(delay)
            if worker.is_cancelled:
                break

            epub_chapter, images = self._make_chapter(name, priority_branch, item)
            if epub_chapter is None:
                self.log_func("Пропускаем главу.")
                continue

            self.book.add_item(epub_chapter)
            for img in images.values():
                try:
                    self.book.add_item(
                        epub.EpubImage(
                            uid=img.name,
                            file_name=img.static_url,
                            media_type=img.media_type,
                            content=get_image_content(img.url, img.extension),
                        )
                    )
                except Exception as e:
                    self.log_func(str(e))
                    continue

            self.log_func(
                f"Скачали {i:>{total_len}}: Том {item.volume:>{volume_len}}. Глава {item.number:>{chap_len}}. {item.name}"
            )

            self.progress_bar_step(1)

    def make_book(self, ranobe_data: dict) -> None:
        self.log_func("\nПодготавливаем книгу...")

        title = ranobe_data.get("rus_name") if ranobe_data.get("rus_name") else ranobe_data.get("name")

        book: epub.EpubBook = epub.EpubBook()
        book.set_title(title)

        book.set_language("ru")
        for author in ranobe_data.get("authors"):
            book.add_author(author.get("name"))

        cover_url = ranobe_data.get("cover").get("default")
        book.set_cover(cover_url.split("/")[-1], requests.get(cover_url).content, False)

        book.add_metadata(
            "DC",
            "subject",
            " ".join([genre.get("name") for genre in ranobe_data.get("genres")]),
        )
        book.add_metadata("DC", "description", ranobe_data.get("summary").replace("\n", "<p>"))
        book.add_metadata("DC", "contributor", "RanobeLib2ebook")
        book.add_metadata("DC", "source", "ranobelib.me")
        book.add_metadata(
            None,
            "meta",
            "",
            {
                "name": "series",
                "content": ranobe_data.get("franchise")[0].get("name")
                if ranobe_data.get("franchise")
                else ranobe_data.get("name"),
            },
        )

        self.log_func("Подготовили книгу.")

        self.book = book
