import os
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import traceback

import pyperclip
from textual import on, work
from textual.app import App, ComposeResult
from textual.validation import Function
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll, Vertical
from textual.worker import Worker, get_current_worker
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
    Switch,
)

from textual_fspicker import SelectDirectory

from src.config import config, VERSION
from src.model import ChapterMeta, Handler, State
from src.api import get_branchs, get_chapters_data, get_latest_release, get_ranobe_data
from src.utils import is_jwt, is_valid_url

title = r"""
     ____                   _          _     ___ ____    ____         _                 _    
    |  _ \ __ _ _ __   ___ | |__   ___| |   |_ _| __ )  |___ \    ___| |__   ___   ___ | | __
    | |_) / _` | '_ \ / _ \| '_ \ / _ \ |    | ||  _ \    __) |  / _ \ '_ \ / _ \ / _ \| |/ /
    |  _ < (_| | | | | (_) | |_) |  __/ |___ | || |_) |  / __/  |  __/ |_) | (_) | (_) |   < 
    |_| \_\__,_|_| |_|\___/|_.__/ \___|_____|___|____/  |_____|  \___|_.__/ \___/ \___/|_|\_\                                                                                      
        """


def update_available() -> bool:
    """Проверяет доступность новой версии."""
    try:
        last_ver = get_latest_release("DustGalaxy", "Ranobe2ebook")
        return last_ver != VERSION
    except Exception as e:
        return False


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
    ebook: Handler = None  # type: ignore
    cd_error_link: int = 0
    cd_error_dir: int = 0
    new_version = False

    def __init__(
        self,
        *,
        handlers: dict[str, Handler],
    ) -> None:
        super().__init__()
        self.handlers = handlers

    BINDINGS = [
        Binding(key="ctrl+q", action="quit", key_display="ctrl + q", description="Выйти"),
        Binding(
            key="i",
            action="open_issue_link()",
            key_display="i",
            description="Нашли ошибку? ↗",
        ),
        Binding(
            key="u",
            action="open_latest_version()",
            key_display="u",
            description="Доступно обновление! ↗" if update_available() else "Детали версии ↗",
        ),
    ]

    def dev_print(self, text: str) -> None:
        # self.query_one("#dev_label").update(text)
        pass

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, name=f"RanobeLIB 2 ebook {VERSION}")
        yield Footer()

        with Vertical():
            with Horizontal(classes="m1-2 horizontal aling-center-middle "):
                yield Input(
                    id="input_link",
                    placeholder="Сcылка на ранобе. Пример: https://ranobelib.me/ru/book/165329--kusuriya-no-hitorigoto-ln-novel",
                    validators=[Function(is_valid_url, "Неправильная ссылка!")],
                    classes="w-frame input",
                )

                yield Button("📋", id="paste_link", variant="primary", classes="mt-1")
                yield Button("🧹", id="clear_link", variant="error", classes="mt-1")
                yield Button("🔐", id="paste_token", variant="warning", classes="mt-1")
            with Horizontal(classes="horizontal m1-2"):
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
                yield Button(
                    "Отстановить и сохранить", id="stop_and_save", variant="error", disabled=True, classes="w-frame"
                )
            yield ProgressBar(
                id="download_progress",
                show_eta=False,
                classes="w-full px-3",
            )

            with VerticalScroll(classes="verticalScroll"):
                with Horizontal(classes="horizontal"):
                    with Vertical(id="settings", classes=" m1-2"):
                        yield Select(
                            (),
                            prompt="Выбрать приоритетную ветку перевода",
                            id="branch_list",
                            classes="w-full mb-1",
                        )
                        yield Label("", id="dev_label", classes="w-full mb-1")
                        with RadioSet(classes="w-full mb-1 h-3"):
                            with Horizontal(classes="horizontal"):
                                yield Label("Включать изображения   ")
                                yield Switch(value=True, id="add_images", classes="swith_wo_border")

                        with RadioSet(classes="w-full mb-1 h-3"):
                            with Horizontal(classes="horizontal"):
                                yield Label("Подгрузить из кеша   ")
                                yield Switch(value=True, id="load_from_cache", classes="swith_wo_border")

                        with RadioSet(id="format", name="format", classes="w-full mb-1"):
                            yield Label("Формат")
                            yield Rule(line_style="heavy", classes="rule")
                            yield RadioButton("EPUB", name="epub", value=True)
                            yield RadioButton("FB2", name="fb2")

                        with RadioSet(id="save_dir", classes="w-full mb-1"):
                            yield Label("Сохранить в папку")
                            yield Rule(line_style="heavy", classes="rule")
                            yield RadioButton("Робочий стол", name="desktop", value=True)
                            yield RadioButton("Документы", name="documents")
                            yield RadioButton("Текущая папка", name="current_folder")
                            yield RadioButton("Другая папка", name="other_folder")
                            yield Input(
                                placeholder="Путь в папке",
                                id="input_save_dir",
                                disabled=True,
                                validators=[Function(os.path.isdir, "Invalid directory!")],
                                classes="input",
                            )
                        yield Label("Задержка между скачиваниями (сек)", id="input_download_delay_label", classes="w-full mb-1")
                        yield Input(
                            id="input_download_delay",
                            placeholder="Задержка между скачиваниями (сек)",
                            type="integer",
                            validators=[Function(is_valid_url, "Неправильная ссылка!")],
                            classes="w-frame input",
                            value = "10"
                        )
                    with Vertical(classes="main-vertical-height w-frame"):
                        with Horizontal(classes="horizontal"):
                            yield Input(
                                id="input_start",
                                placeholder="C",
                                type="integer",
                                disabled=True,
                                classes="w-frame input",
                            )
                            yield Input(
                                id="input_end",
                                placeholder="Кол-во",
                                type="integer",
                                disabled=True,
                                classes="w-frame input",
                            )
                        yield Label("", id="chapters_count", classes="w-full m1-2")

                        yield Log(id="log", classes="w-frame")
                        yield Log(id="chapter_list", auto_scroll=False, classes="w-frame")

    def action_open_issue_link(self) -> None:
        webbrowser.open("https://github.com/DustGalaxy/RanobeLib2ebook/issues")

    def action_open_latest_version(self) -> None:
        webbrowser.open("https://github.com/DustGalaxy/RanobeLib2ebook/releases/latest")

    @on(Input.Changed, "#input_link")
    def show_invalid_reasons(self, event: Input.Changed) -> None:
        if not event.validation_result.is_valid:  # type: ignore
            if self.cd_error_link == 0:
                self.notify("Неправильная ссылка", severity="error", timeout=2)
                self.cd_error_link = 7
            else:
                self.cd_error_link -= 1
            self.query_one("#check_link").disabled = True
        else:
            self.cd_error_link = 0
            self.query_one("#check_link").disabled = False

    @on(Input.Changed, "#input_save_dir")
    def show_dir(self, event: Input.Changed) -> None:
        if not event.validation_result.is_valid:  # type: ignore
            if self.cd_error_dir == 0:
                self.notify("Неправильный путь", severity="error", timeout=2)
                self.cd_error_dir = 7
            else:
                self.cd_error_dir -= 1
            self.state.is_dir_selected = False
        else:
            self.cd_error_dir = 0
            self.dir = event.value
            self.state.is_dir_selected = True

    @on(Input.Changed, "#input_start")
    def show_from_chapter(self, event: Input.Changed) -> None:
        if event.validation_result.is_valid:  # type: ignore
            start: int = int(event.value)
            end: Input = self.query_one("#input_end")  # type: ignore

            p_bar: ProgressBar = self.query_one("#download_progress")  # type: ignore

            if end.value not in ("", None):
                start = start - 1

                amount = int(end.value)
                tmp = self.chapters_data[start : start + amount]
                len_tmp = len(tmp)
                if len_tmp != 0:
                    p_bar.update(total=len_tmp)
                    self.start = start
                    self.query_one("#chapters_count").update(  # type: ignore
                        f"С: Том {tmp[0].volume}. Глава {tmp[0].number}. По: Том {tmp[-1].volume}. Глава {tmp[-1].number}. - глав: {len_tmp}."
                    )

    @on(Input.Changed, "#input_end")
    def show_to_chapter(self, event: Input.Changed) -> None:
        if event.validation_result.is_valid:  # type: ignore
            end: int = int(event.value)
            start: Input = self.query_one("#input_start")  # type: ignore

            p_bar: ProgressBar = self.query_one("#download_progress")  # type: ignore

            if start.value not in ("", None):
                start = int(start.value)  # type: ignore
                start = start - 1  # type: ignore
                amount = end

                tmp = self.chapters_data[start : start + amount]  # type: ignore
                len_tmp = len(tmp)

                if len_tmp != 0:
                    p_bar.update(total=len_tmp)
                    self.amount = amount
                    self.query_one("#chapters_count").update(  # type: ignore
                        f"С: Том {tmp[0].volume}. Глава {tmp[0].number}. По: Том {tmp[-1].volume}. Глава {tmp[-1].number}. - глав: {len_tmp}."
                    )

    @on(Button.Pressed, "#check_link")
    def check_link(self, event: Button.Pressed) -> None:
        log: Log = self.query_one("#log")  # type: ignore

        self.dev_print("Check link")
        self.clear_all()

        url = urlparse(self.query_one("#input_link").value)  # type: ignore
        self.slug = url.path.split("/")[-1]

        log.write_line("Получаем данные о ранобе...")
        self.ranobe_data = get_ranobe_data(self.slug)  # type: ignore

        if self.ranobe_data is None:
            log.write_line("Не удалось получить данные о ранобе.")
            log.write_line("Либо такого ранобє нету, либо для него требуется авторизация.")
            log.write_line("Если вы уже авторизовивались, сделайте это еще раз.")
            return
        log.write_line("Получили данные о ранобе.")
        log.write_line("\nПолучаем список ветвей перевода...")
        branchs = get_branchs(self.ranobe_data.get("id"))  # type: ignore

        if branchs is None or len(branchs) == 0:
            log.write_line("Не удалось получить список ветвей перевода. \nБудет использоватся главная ветвь.")
        else:
            log.write_line("Получили список ветвей перевода.")

        options: list[tuple[str, str]] = []
        for i, branch in enumerate(branchs):  # type: ignore
            options.append(
                (
                    f"{branch.get('name')}. Переводчики: {' & '.join([team.get('name') for team in branch.get('teams')])}",
                    str(branch.get("id")),
                )
            )

        if len(options) == 0:
            options = [("Main branch", "0")]
            self.query_one("#branch_list").set_options(options)  # type: ignore
            self.query_one("#branch_list").value = options[0][1]  # type: ignore
        else:
            self.query_one("#branch_list").set_options(options)  # type: ignore
            self.query_one("#branch_list").value = options[0][1]  # type: ignore

        log.write_line("\nПолучаем список глав...")
        self.chapters_data = get_chapters_data(self.slug)  # type: ignore
        if self.chapters_data is None:
            log.write_line("Не удалось получить список глав.")
            return

        self.state.is_data_loaded = True
        log.write_line("Получили список глав.")

        self.query_one("#input_start").value = "1"  # type: ignore
        self.query_one("#input_end").value = str(len(self.chapters_data))  # type: ignore

        total_len = len(str(len(self.chapters_data)))
        chap_len = len(str(max(self.chapters_data, key=lambda x: len(str(x.number))).number))
        volume_len = len(str(self.chapters_data[-1].volume))

        self.query_one("#chapter_list").write_lines(  # pyright: ignore[reportAttributeAccessIssue]
            [
                f"{i:>{total_len}}: Том {chapter.volume:>{volume_len}}. Глава {chapter.number:>{chap_len}}. {chapter.name}"
                for i, chapter in enumerate(self.chapters_data, 1)
            ]
        )

        log.write_line("\nГотовы к скачиванию!")

        self.state.is_chapters_selected = True
        dir_radio_set: RadioSet = self.query_one("#save_dir")  # type: ignore
        if dir_radio_set.pressed_button.name == "other_folder" and not self.dir:  # type: ignore
            self.state.is_dir_selected = False
        else:
            self.state.is_dir_selected = True
        self.query_one("#download").disabled = False
        self.query_one("#input_start").disabled = False
        self.query_one("#input_end").disabled = False

    @on(Button.Pressed, "#paste_token")
    def paste_token(self, event: Button.Pressed) -> None:
        token = pyperclip.paste()
        if not is_jwt(token):
            self.notify("Некоректный токен", severity="error", timeout=2)
            return
        config.token = token
        event.button.variant = "success"  # success("🔓")
        event.button.label = "🔓"
        self.notify("Токен скопирован", timeout=2)

    @on(Button.Pressed, "#clear_link")
    def clear_link(self, event: Button.Pressed) -> None:
        self.query_one("#input_link").value = ""  # type: ignore
        self.notify("Ссылка очищенна", timeout=2)

    @on(Button.Pressed, "#paste_link")
    def paste_link(self, event: Button.Pressed) -> None:
        clipboard_content = pyperclip.paste()
        if is_valid_url(clipboard_content):
            self.query_one("#input_link").value = clipboard_content  # type: ignore
            self.notify("Ссылка вставленна", timeout=2)
        else:
            self.notify("Некоректная ссылка", severity="error", timeout=2)

    @work(name="make_ebook_worker", exclusive=True, thread=True)
    async def make_ebook_worker(self) -> None:
        log: Log = self.query_one("#log")  # type: ignore
        p_bar: ProgressBar = self.query_one("#download_progress")  # type: ignore

        format = self.query_one("#format").pressed_button.name  # type: ignore
        add_images = self.query_one("#add_images").value  # type: ignore
        load_from_cache = self.query_one("#load_from_cache").value  # type: ignore

        input_download_delay: int = 10
        if self.query_one("#input_download_delay").value not in ("", None):
            input_download_delay = int(self.query_one("#input_download_delay").value)
        Handler_: Handler = self.handlers[format]

        self.ebook = Handler_(log_func=log.write_line, progress_bar_step=p_bar.advance)  # type: ignore
        self.ebook.with_images = add_images
        self.ebook.load_from_cache = load_from_cache
        self.ebook.input_download_delay = input_download_delay
        try:
            self.ebook.make_book(self.ranobe_data)
            log.write_line("Создали книгу")
        except Exception as e:
            log.write_line(str(e))

    @work(name="fill_ebook_worker", exclusive=True, thread=True)
    async def fill_ebook_worker(self) -> None:
        log: Log = self.query_one("#log")  # type: ignore
        self.query_one("#stop_and_save").disabled = False
        try:
            worker = get_current_worker()
            self.ebook.fill_book(
                self.slug, self.priority_branch, self.chapters_data[self.start : self.start + self.amount], worker
            )

        except Exception as e:
            log.write_line("".join(traceback.format_exception(type(e), e, e.__traceback__)))

    @work(name="end_ebook_worker", exclusive=True, thread=True)
    async def end_ebook_worker(self) -> None:
        log: Log = self.query_one("#log")  # type: ignore
        self.query_one("#stop_and_save").disabled = True
        try:
            self.ebook.end_book()

        except Exception as e:
            log.write_line(str(e))

    @work(name="save_ebook_worker", exclusive=True, thread=True)
    async def save_ebook_worker(self) -> None:
        log: Log = self.query_one("#log")  # type: ignore

        try:
            log.write_line("\nСохраняем книгу...")
            self.ebook.save_book(self.dir)
        except Exception as e:
            log.write_line(str(e))
        self.query_one("#check_link").disabled = False

    @on(Worker.StateChanged)
    def worker_manage(self, event: Worker.StateChanged) -> None:
        match event.worker.name:
            case "make_ebook_worker":
                match event.state.name:
                    case "SUCCESS":
                        self.fill_ebook_worker()
            case "fill_ebook_worker":
                match event.state.name:
                    case "SUCCESS" | "CANCELLED" | "ERROR":
                        self.end_ebook_worker()
            case "end_ebook_worker":
                match event.state.name:
                    case "SUCCESS":
                        self.save_ebook_worker()

    @on(Button.Pressed, "#download")
    def download(self, event: Button.Pressed) -> None:
        if all([i for i in self.state.__dict__.values()]) and self.dir:
            self.dev_print("Download")
            self.query_one("#download").disabled = True
            self.query_one("#check_link").disabled = True
            self.query_one("#input_start").disabled = True
            self.query_one("#input_end").disabled = True

            self.make_ebook_worker()
        else:
            self.dev_print(str([(i, j) for i, j in self.state.__dict__.items()]))

    @on(Button.Pressed, "#stop_and_save")
    def stop_and_save(self, event: Button.Pressed) -> None:
        self.end_ebook_worker()

    @on(Select.Changed, "#branch_list")
    def branch_list(self, event: Select.Changed) -> None:
        if event.select.value != Select.BLANK:
            self.state.is_branch_selected = True
            self.priority_branch = event.select.value  # type: ignore
            self.dev_print(event.select.value)  # type: ignore

    @on(RadioSet.Changed)
    def set_option(self, event: RadioSet.Changed) -> None:
        match event.radio_set.id:
            case "save_dir":
                self.dev_print(event.radio_set.pressed_button.label)  # type: ignore
                input_save_dir: Input = self.query_one("#input_save_dir")  # type: ignore
                input_save_dir.disabled = True
                match event.radio_set.pressed_button.name:  # type: ignore
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
                        self.dir = None  # type: ignore
                        input_save_dir.disabled = False

                        self.push_screen(
                            SelectDirectory(
                                location=input_save_dir.value if input_save_dir.value else ".",
                                title="Выберите папку",
                                select_button="Выбрать",
                                cancel_button="Отмена",
                            ),
                            callback=self.show_selected,
                        )

    def show_selected(self, to_show: Path | None) -> None:
        self.query_one("#input_save_dir").value = "" if to_show is None else str(to_show)  # type: ignore
        self.dev_print("Cancelled" if to_show is None else str(to_show))

    def clear_all(self) -> None:
        self.query_one("#download_progress").update(total=None, progress=0)  # type: ignore
        self.query_one("#chapter_list").clear()  # type: ignore
        self.query_one("#branch_list").clear()  # type: ignore
        self.query_one("#branch_list").set_options([])  # type: ignore
        self.query_one("#input_start").clear()  # type: ignore
        self.query_one("#input_end").clear()  # type: ignore
