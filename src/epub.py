import os
import re
import time
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from ebooklib import epub

from src.model import ChapterData, ChapterMeta, Image, Handler
from src.api import get_chapter, get_image_content


class EpubHandler(Handler):
    book: epub.EpubBook
    style_tags = {
        "bold": "b",
        "italic": "i",
        "underline": "ins",
        "strike": "del",
    }

    def __init__(self, *args, **kwargs):
        super(EpubHandler, self).__init__(*args, **kwargs)
        self.book = epub.EpubBook()

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
                    imageE = self._insert_image(image) if self.with_images else ET.Element("span")
                    tags.append(imageE)
                except Exception as e:
                    self.log_func("Ошибка: " + str(e))

                continue
            tags.append(ET.fromstring(str(tag)))

        return tags

    def _insert_image(self, image: Image) -> ET.Element:
        for item in self.book.items:
            if isinstance(item, epub.EpubImage) and item.content == image.content:
                return ET.Element("img", attrib={"src": item.file_name})

        self.book.add_item(
            epub.EpubImage(
                uid=image.uid,
                file_name=image.static_url,
                media_type=image.media_type,
                content=image.content,
            )
        )
        return ET.Element("img", attrib={"src": image.static_url})

    def _parse_marks(self, marks: list, tag: ET.Element, text: str, _index: int = 0) -> ET.Element:
        if _index >= len(marks):
            tag.text = text
            return tag

        style_type = self.style_tags.get(marks[_index].get("type"), "span")
        new_tag = ET.Element(style_type)
        tag.append(self._parse_marks(marks, new_tag, text, _index + 1))
        return tag

    def _parse_paragraph(self, paragraph: dict, element: str = "p") -> ET.Element:
        paragraphE = ET.Element(element)

        attrs = paragraph.get("attrs")
        if attrs:
            aling = attrs.get("textAlign")
            paragraphE.attrib["style"] = f"text-align: {aling or 'left'};"

        if "content" not in paragraph:
            return paragraphE

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

    def _tag_parser(self, tag: dict, **kwargs) -> ET.Element:
        tag_type = tag.get("type")
        match tag_type:
            case "image":
                images: dict[str, Image] = kwargs.get("images")
                if not images:
                    return ET.Element("span")
                img_name = tag.get("attrs").get("images")[-1].get("image")
                img = images.get(img_name)

                return self._insert_image(img) if img and self.with_images else ET.Element("span")

            case "paragraph":
                return self._parse_paragraph(tag)

            case "horizontalRule":
                return ET.Element("hr", attrib={"style": "width: 100%;"})

            case "bulletList" | "orderedList":
                list_items = tag.get("content")
                listE = self._parse_list(list_items, tag_type)
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
                    blockquoteE.append(self._tag_parser(b_tag, kwargs=kwargs))
                return blockquoteE

    def _parse_doc(self, chapter: ChapterData) -> list[ET.Element]:
        attachments = chapter.attachments
        img_base_url = "https://ranobelib.me"
        images: dict[str, Image] = {}
        tags: list[ET.Element] = []

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

        for item in chapter.content:
            tmp = self._tag_parser(item, images=images)
            tags.append(tmp)

        return tags

    def _make_chapter(self, slug: str, priority_branch: str, item: ChapterMeta) -> epub.EpubHtml | None:
        try:
            chapter: ChapterData = get_chapter(
                slug,
                priority_branch,
                item.number,
                item.volume,
            )
        except Exception as e:
            self.log_func("Ошибка: " + str(e))
            return None

        chapter_title = f"Том {item.volume}. Глава {item.number}. {item.name}"

        epub_chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=item.number + "_" + item.volume + ".xhtml",
        )

        tags: list[ET.Element] = []
        if chapter.type == "html":
            tags: list[str] = self._parse_html(chapter)
        elif chapter.type == "doc":
            tags: list[ET.Element] = self._parse_doc(chapter)
        else:
            self.log_func("Неизвестный тип главы! Невозможно преобразовать в EPUB!")
            return None

        hmtl_str = "".join([ET.tostring(tag, encoding="unicode", method="html") for tag in tags])

        soup = BeautifulSoup(hmtl_str, "html.parser")
        for span in soup.find_all("span"):
            if not span.attrs:
                span.unwrap()

        epub_chapter.set_content(f"<h1>{chapter_title}</h1>" + str(soup))

        return epub_chapter

    def fill_book(
        self,
        name: str,
        priority_branch: str,
        chapters_data: list[ChapterMeta],
        worker,
        delay: float = 0.5,
    ) -> None:
        self.max_chapter = str(chapters_data[-1].number)
        self.min_chapter = str(chapters_data[0].number)

        total_len = len(str(len(chapters_data)))
        chap_len = len(str(max(chapters_data, key=lambda x: len(str(x.number))).number))
        volume_len = len(str(chapters_data[-1].volume))

        self.log_func(f"\nНачинаем скачивать главы: {len(chapters_data)}")

        for i, chapter_meta in enumerate(chapters_data, 1):
            time.sleep(delay)
            if worker.is_cancelled:
                break

            chapter = self._make_chapter(name, priority_branch, chapter_meta)
            if chapter:
                self.book.add_item(chapter)

                self.log_func(
                    f"Скачали {i:>{total_len}}: Том {chapter_meta.volume:>{volume_len}}. Глава {chapter_meta.number:>{chap_len}}. {chapter_meta.name}"
                )
            else:
                self.log_func("Пропускаем главу.")

            self.progress_bar_step(1)

    def save_book(self, dir: str) -> None:
        safe_title = re.sub(r'[<>:"/\\|?*]', "", self.book.title)
        file_path = os.path.join(dir, f"{safe_title}.epub")
        epub.write_epub(file_path, self.book)

        self.log_func(f"Книга {self.book.title} сохранена в формате Epub.")
        self.log_func(f"В каталоге {dir} создана книга {safe_title}.epub.")
        self.book = None

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
            {"name": "series_index", "content": f"Главы c {self.min_chapter} по {self.max_chapter}"},
        )

    def make_book(self, ranobe_data: dict) -> None:
        self.log_func("\nПодготавливаем книгу...")

        title = ranobe_data.get("rus_name") if ranobe_data.get("rus_name") else ranobe_data.get("name")

        book: epub.EpubBook = epub.EpubBook()
        book.set_title(title)

        book.set_language("ru")
        for author in ranobe_data.get("authors"):
            book.add_author(author.get("name"))

        cover_url = ranobe_data.get("cover").get("default")
        book.set_cover(cover_url.split("/")[-1], get_image_content(cover_url, cover_url.split(".")[-1]), False)

        book.add_metadata(
            "DC",
            "subject",
            " ".join([genre.get("name") for genre in ranobe_data.get("genres")]),
        )
        book.add_metadata("DC", "description", ranobe_data.get("summary").replace("\n", "<p>"))
        book.add_metadata("DC", "contributor", "Ranobe2ebook")
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
