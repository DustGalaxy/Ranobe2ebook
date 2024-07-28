import os
import re
from pathlib import Path
from typing import Literal
from urllib import parse
from urllib.parse import urlparse

from textual import on, work
from textual.app import App, ComposeResult
from textual.color import Gradient
from textual.validation import Function
from textual.containers import Horizontal, VerticalScroll, Vertical
from textual.widgets import (
    Footer,
    Header,
    RadioButton,
    RadioSet,
    Input,
    Label,
    Rule,
    Button,
    Select,
    ProgressBar,
    Log,
)

from textual_fspicker import SelectDirectory

from src.model import ChapterMeta, Handler, State
from src.api import get_branchs, get_chapters_data, get_ranobe_data

title = r"""
     ____                   _          _     ___ ____    ____         _                 _    
    |  _ \ __ _ _ __   ___ | |__   ___| |   |_ _| __ )  |___ \    ___| |__   ___   ___ | | __
    | |_) / _` | '_ \ / _ \| '_ \ / _ \ |    | ||  _ \    __) |  / _ \ '_ \ / _ \ / _ \| |/ /
    |  _ < (_| | | | | (_) | |_) |  __/ |___ | || |_) |  / __/  |  __/ |_) | (_) | (_) |   < 
    |_| \_\__,_|_| |_|\___/|_.__/ \___|_____|___|____/  |_____|  \___|_.__/ \___/ \___/|_|\_\                                                                                      
        """


class Ranobe2ebook(App):
    CSS_PATH = "../style.tcss"
    slug: str
    ranobe_data: dict
    chapters_data: list[ChapterMeta]
    priority_branch: str
    dir: str = os.path.normpath(os.path.expanduser("~/Desktop"))
    start: int
    amount: int
    state: State = State()

    def __init__(
        self,
        *,
        handlers: dict[Literal["fb2", "epub"], Handler],
    ) -> None:
        super().__init__()
        self.handlers = handlers

    def dev_print(self, text: str) -> None:
        # self.query_one("#dev_label").update(text)
        pass

    def is_ready_download(self) -> bool:
        return all([i for i in self.state.__dict__.values()])

    def compose(self) -> ComposeResult:
        gradient = Gradient.from_colors(
            "#881177",
            "#aa3355",
            "#cc6666",
            "#ee9944",
            "#eedd00",
            "#99dd55",
            "#44dd88",
            "#22ccbb",
            "#00bbcc",
            "#0099cc",
            "#3366bb",
            "#663399",
        )
        yield Header(show_clock=True, name="RanobeLIB 2 ebook")
        yield Footer()
        with Vertical():
            yield Label(title)
            yield Input(
                id="input_link",
                placeholder="Сcылка на ранобе. Пример: https://ranobelib.me/ru/book/165329--kusuriya-no-hitorigoto-ln-novel",
                validators=[Function(is_valid_url, "Invalid link!")],
            )
            yield Label("", id="url_errors", classes="w-full m1-2")
            with Horizontal(classes="m1-2"):
                yield Button(
                    "Проверка ссылки",
                    id="check_link",
                    disabled=True,
                    variant="primary",
                    classes="w-frame",
                )
                yield Button(
                    "Скачать",
                    id="download",
                    disabled=True,
                    variant="success",
                    classes="w-frame",
                )
                yield Button("Выход", id="exit", variant="error", classes="w-frame")
            yield Rule(line_style="heavy")
            with Horizontal():
                with Vertical():
                    yield Select(
                        (),
                        prompt="Выбрать приоритетную ветку перевода",
                        id="branch_list",
                        classes="w-full m1-2",
                    )
                    yield Label("", id="dev_label", classes="w-full m1-2")
                    with RadioSet(id="format", name="format", classes="w-full m1-2"):
                        yield Label("Формат")
                        yield Rule(line_style="heavy")
                        yield RadioButton("EPUB с картинками 📝 + 🖼", name="epub", value=True)
                        yield RadioButton("FB2 без картинок 📝", name="fb2")
                    with RadioSet(id="save_dir", classes="w-full m1-2"):
                        yield Label("Сохранить в папку")
                        yield Rule(line_style="heavy")
                        yield RadioButton("Робочий стол", name="desktop", value=True)
                        yield RadioButton("Документы", name="documents")
                        yield RadioButton("Текущая папка", name="current_folder")
                        yield RadioButton("Другая папка", name="other_folder")
                        yield Input(
                            placeholder="Путь в папке",
                            id="input_save_dir",
                            disabled=True,
                            validators=[Function(os.path.isdir, "Invalid directory!")],
                        )
                        yield Label("", id="dir_errors", classes="w-frame mx-2")

                yield Rule(orientation="vertical", line_style="heavy", classes="height-28")
                with VerticalScroll(classes="height-28 mx-1"):
                    with Horizontal(classes=""):
                        yield Input(
                            id="input_start",
                            placeholder="C",
                            type="integer",
                            disabled=True,
                            classes="w-frame",
                        )
                        yield Input(
                            id="input_end",
                            placeholder="Кол-во",
                            type="integer",
                            disabled=True,
                            classes="w-frame",
                        )
                    yield Label("", id="chapters_count", classes="w-full m1-2")
                    yield ProgressBar(
                        id="download_progress",
                        gradient=gradient,
                        show_eta=False,
                        classes="w-full",
                    )
                    yield Log(id="log")
                    yield Log(
                        id="chapter_list",
                        auto_scroll=False,
                    )

    def on_ready(self) -> None:
        pass

    @on(Input.Changed, "#input_link")
    def show_invalid_reasons(self, event: Input.Changed) -> None:
        if not event.validation_result.is_valid:
            self.query_one("#url_errors").update("Неправильная ссылка!")
            self.query_one("#check_link").disabled = True
        else:
            self.query_one("#url_errors").update("")
            self.query_one("#check_link").disabled = False

    @on(Input.Changed, "#input_save_dir")
    def show_dir(self, event: Input.Changed) -> None:
        if not event.validation_result.is_valid:
            self.query_one("#dir_errors").update("Неправильный путь!")
            self.state.is_dir_selected = False
        else:
            self.query_one("#dir_errors").update("")
            self.dir = event.value
            self.state.is_dir_selected = True

    @on(Input.Changed, "#input_start")
    def show_from_chapter(self, event: Input.Changed) -> None:
        if event.validation_result.is_valid:
            start: int = int(event.value)
            end: Input = self.query_one("#input_end")

            p_bar: ProgressBar = self.query_one("#download_progress")

            if end.value not in ("", None):
                start = start - 1

                amount = int(end.value)
                tmp = self.chapters_data[start : start + amount]
                len_tmp = len(tmp)
                if len_tmp != 0:
                    p_bar.update(total=len_tmp)
                    self.start = start
                    self.query_one("#chapters_count").update(
                        f"С: Том {tmp[0].volume}. Глава {tmp[0].number}. По: Том {tmp[-1].volume}. Глава {tmp[-1].number}. - глав: {len_tmp}."
                    )

    @on(Input.Changed, "#input_end")
    def show_to_chapter(self, event: Input.Changed) -> None:
        if event.validation_result.is_valid:
            end: int = int(event.value)
            start: Input = self.query_one("#input_start")

            p_bar: ProgressBar = self.query_one("#download_progress")

            if start.value not in ("", None):
                start = int(start.value)
                start = start - 1
                amount = end

                tmp = self.chapters_data[start : start + amount]
                len_tmp = len(tmp)

                if len_tmp != 0:
                    p_bar.update(total=len_tmp)
                    self.amount = amount
                    self.query_one("#chapters_count").update(
                        f"С: Том {tmp[0].volume}. Глава {tmp[0].number}. По: Том {tmp[-1].volume}. Глава {tmp[-1].number}. - глав: {len_tmp}."
                    )

    @on(Button.Pressed, "#check_link")
    def check_link(self, event: Button.Pressed) -> None:
        log: Log = self.query_one("#log")

        self.dev_print("Check link")
        self.clear_all()

        url = parse.urlparse(self.query_one("#input_link").value)
        self.slug = url.path.split("/")[-1]

        log.write_line("Получаем данные о ранобе...")
        self.ranobe_data = get_ranobe_data(self.slug)
        if self.ranobe_data is None:
            log.write_line("Не удалось получить данные о ранобе.")
            return
        log.write_line("Получили данные о ранобе.")

        log.write_line("\nПолучаем список ветвей перевода...")
        branchs = get_branchs(self.ranobe_data.get("id"))

        if branchs is None or len(branchs) == 0:
            log.write_line("Не удалось получить список ветвей перевода. \nБудет использоватся главная ветвь.")
        else:
            log.write_line("Получили список ветвей перевода.")

        options: list[tuple[str, str]] = []
        for i, branch in enumerate(branchs):
            options.append(
                (
                    f"{branch.get('name')}. Переводчики: {' & '.join([team.get('name') for team in branch.get('teams')])}",
                    str(branch.get("id")),
                )
            )

        if len(options) == 0:
            options = [("Main branch", "0")]
            self.query_one("#branch_list").set_options(options)
            self.query_one("#branch_list").value = options[0][1]
        else:
            self.query_one("#branch_list").set_options(options)
            self.query_one("#branch_list").value = options[0][1]

        log.write_line("\nПолучаем список глав...")
        self.chapters_data = get_chapters_data(self.slug)
        if self.chapters_data is None:
            log.write_line("Не удалось получить список глав.")
            return

        self.state.is_data_loaded = True
        log.write_line("Получили список глав.")

        self.query_one("#input_start").value = "1"
        self.query_one("#input_end").value = str(len(self.chapters_data))

        total_len = len(str(len(self.chapters_data)))
        chap_len = len(str(max(self.chapters_data, key=lambda x: len(str(x.number))).number))
        volume_len = len(str(self.chapters_data[-1].volume))

        self.query_one("#chapter_list").write_lines(
            [
                f"{i:>{total_len}}: Vol {chapter.volume:>{volume_len}}. Chap {chapter.number:>{chap_len}}. {chapter.name}"
                for i, chapter in enumerate(self.chapters_data, 1)
            ]
        )

        log.write_line("\nГотовы к скачиванию!")

        self.state.is_chapters_selected = True
        dir_radio_set: RadioSet = self.query_one("#save_dir")
        if dir_radio_set.pressed_button.name == "other_folder" and not self.dir:
            self.state.is_dir_selected = False
        else:
            self.state.is_dir_selected = True
        self.query_one("#download").disabled = False
        self.query_one("#input_start").disabled = False
        self.query_one("#input_end").disabled = False

    @work(exclusive=True, thread=True)
    async def ebook_worker(self) -> None:
        log: Log = self.query_one("#log")
        p_bar: ProgressBar = self.query_one("#download_progress")

        format = self.query_one("#format").pressed_button.name

        Handler_: Handler = self.handlers[format]

        ebook = Handler_(log_func=log.write_line, progress_bar_step=p_bar.advance)
        await ebook.make_book(self.ranobe_data)
        await ebook.fill_book(
            self.slug, self.priority_branch, self.chapters_data[self.start : self.start + self.amount]
        )
        log.write_line("\nСохраняем книгу...")
        await ebook.save_book(self.dir)
        self.query_one("#check_link").disabled = False

    @on(Button.Pressed, "#download")
    async def download(self, event: Button.Pressed) -> None:
        if self.is_ready_download() and self.dir:
            self.dev_print("Download")
            self.query_one("#download").disabled = True
            self.query_one("#check_link").disabled = True
            self.query_one("#input_start").disabled = True
            self.query_one("#input_end").disabled = True

            self.ebook_worker()
        else:
            self.dev_print(str([(i, j) for i, j in self.state.__dict__.items()]))

    @on(Button.Pressed, "#exit")
    def app_exit(self, event: Button.Pressed) -> None:
        self.app.exit()

    @on(Select.Changed, "#branch_list")
    def select_branch(self, event: Select.Changed) -> None:
        if event.select.value != Select.BLANK:
            self.state.is_branch_selected = True
            self.priority_branch = event.select.value
            self.dev_print(event.select.value)

    @on(RadioSet.Changed)
    def set_option(self, event: RadioSet.Changed) -> None:
        match event.radio_set.id:
            case "format":
                match event.radio_set.pressed_button.name:
                    case "epub":
                        self.dev_print("EPUB")
                    case "fb2":
                        self.dev_print("FB2")

            case "save_dir":
                self.dev_print(event.radio_set.pressed_button.label)
                self.query_one("#dir_errors").update("")
                self.query_one("#input_save_dir").disabled = True
                match event.radio_set.pressed_button.name:
                    case "desktop":
                        self.state.is_dir_selected = True

                        self.dir = os.path.normpath(os.path.expanduser("~/Desktop"))
                        self.dev_print(self.dir)
                    case "documents":
                        self.state.is_dir_selected = True
                        self.dir = os.path.normpath(os.path.expanduser("~/Documents"))
                        self.dev_print(self.dir)
                    case "current_folder":
                        self.state.is_dir_selected = True
                        self.dir = os.getcwd()
                        self.dev_print(self.dir)
                    case "other_folder":
                        self.state.is_dir_selected = False
                        self.dir = None
                        self.query_one("#input_save_dir").disabled = False
                        self.push_screen(
                            SelectDirectory(
                                title="Выберите папку",
                            ),
                            callback=self.show_selected,
                        )

    def show_selected(self, to_show: Path | None) -> None:
        self.query_one("#input_save_dir").value = "" if to_show is None else str(to_show)
        self.dev_print("Cancelled" if to_show is None else str(to_show))

    def clear_all(self) -> None:
        self.query_one("#download_progress").update(total=None, progress=0)
        self.query_one("#chapter_list").clear()
        self.query_one("#branch_list").clear()
        self.query_one("#branch_list").set_options([])
        self.query_one("#input_start").clear()
        self.query_one("#input_end").clear()


def is_valid_url(url) -> bool:
    parsed = urlparse(url)

    if all([parsed.scheme == "https", parsed.netloc == "ranobelib.me", parsed.path]):
        pattern = re.compile(r"^/ru/book/.*")
        return bool(pattern.match(parsed.path))

    return False
