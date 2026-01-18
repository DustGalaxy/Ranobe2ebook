import io
import json
import time
from urllib.parse import urlparse

from PIL import Image
import PIL
import cloudscraper
import requests
from requests.exceptions import RequestException, Timeout

from src.cache import cache_chapter, get_cache_path
from src.config import config
from src.model import Attachment, ChapterData, ChapterMeta
from src.utils import is_html, is_url

from typing import Callable


def get_base_api_url() -> str | None:
    response = requests.get(
        f"https://gist.githubusercontent.com/DustGalaxy/958d8a9fe76d7253d1511d99d180d1c5.txt?nocache={int(time.time())}"
    )
    if response.status_code == 200:
        return str(response.content.decode("utf-8")).strip()


BASE_API_URL = get_base_api_url()
HOST = urlparse(BASE_API_URL).hostname


def get_latest_release(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    response = requests.get(url)
    if response.ok:
        data = response.json()
        return data["tag_name"]
    else:
        raise Exception(f"Ошибка запроса: {response.status_code} - {response.text}")


def get_branchs(ranobe_id: str) -> dict | None:
    url = f"{BASE_API_URL}/branches/{ranobe_id}?team_defaults=1"

    response = requests.get(
        url,
        headers={
            "Priority": "u=0",
            "Origin": "https://ranobelib.me",
            "Referer": "https://ranobelib.me/",
            "Authorization": f"Bearer {config.token}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Host": HOST,
            "Sec-Gpc": "1",
            "Site-Id": "3",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        },
    )

    if response.status_code != 200:
        return None

    return response.json().get("data")


def get_ranobe_data(name: str) -> dict | None:
    url_base = f"{BASE_API_URL}/manga/{name}?"
    url = url_base + "&".join(
        [
            f"fields[]={item}"
            for item in [
                "authors",
                "summary",
                "genres",
                "chap_count",
                "releaseDate",
                "franchise",
                "rate",
            ]
        ]
    )
    response = requests.get(
        url,
        headers={
            "Origin": "https://ranobelib.me",
            "Referer": "https://ranobelib.me/",
            "Authorization": f"Bearer {config.token}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Host": HOST,
            "Sec-Gpc": "1",
            "Site-Id": "3",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        },
    )
    if response.status_code != 200:
        return None

    return response.json().get("data")


def get_chapters_data(name: str) -> list[ChapterMeta] | None:
    url = f"{BASE_API_URL}/manga/{name}/chapters"

    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {config.token}"},
    )
    if response.status_code != 200:
        return None
    chapters = [
        ChapterMeta(name=data.get("name"), number=data.get("number"), volume=data.get("volume"))
        for data in response.json().get("data")
    ]

    return chapters


def get_image_content(url: str, format: str, cover: bool = False) -> bytes:
    headers = {
        "Client-Time-Zone": "Europe/Kyiv",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
        "Host": "cover.imglib.info",
        "Origin": "https://ranobelib.me",
        "Referer": "https://ranobelib.me/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Gpc": "1",
        "Site-Id": "3",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0",
    }
    try:
        if format.upper() == "JPG":
            format = "JPEG"

        if not is_url(url):
            return b""

        for _ in range(3):
            try:
                if cover:
                    response = requests.get(url, headers=headers, stream=True, timeout=10)
                else:
                    scraper = cloudscraper.create_scraper()
                    response = scraper.get(url, stream=True, timeout=10)

                break
            except requests.exceptions.ChunkedEncodingError:
                continue

        match response.status_code:
            case 200:
                with Image.open(io.BytesIO(response.content)) as img:
                    with io.BytesIO() as io_buf:
                        img.save(io_buf, format=format, quality=70)
                        io_buf.seek(0)
                        return io_buf.read()

            case 404:
                raise Exception(
                    f"Error {response.status_code}: {response.reason}. {url=} \nКартинка не найдена по ссылке в API. Пропускаем картинку."
                )

            case _:
                raise Exception(
                    f"Error {response.status_code}: {response.reason}. {url=} \nНе удалось получить картинку. Пропускаем картинку."
                )

    except PIL.UnidentifiedImageError:
        raise Exception("Что то не так с картинкой. Пропускаем картинку.")

    except requests.exceptions.ChunkedEncodingError:
        raise Exception("Ошибка при получении картинки. Пропускаем картинку.")

    except Exception as e:
        raise Exception(e)


def _retry_delays():
    # 10, 20, 30, 60
    yield 10
    yield 20
    yield 30
    while True:
        yield 60


def get_chapter(
    ranobe_name: str,
    priority_branch: str,
    number: int,
    volume: int,
    log_func: Callable,
    load_from_cache: bool,
    save_to_cache: bool,
    input_download_delay: float = 0.5,
) -> "ChapterData":
    # Путь к кешу
    cache_path = get_cache_path(ranobe_name, priority_branch, number, volume)

    # Попытка загрузки из кеша
    if load_from_cache and cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as f:
                cached_data = json.load(f)
            log_func(f"Загружено из кеша: {cache_path}")

            attachments = [Attachment(**item) for item in cached_data.get("attachments", [])]

            return ChapterData(
                id=cached_data["id"],
                number=cached_data["number"],
                volume=cached_data["volume"],
                type=cached_data["type"],
                content=cached_data["content"],
                attachments=attachments,
            )
        except Exception as e:
            log_func(f"Ошибка при чтении кеша: {e}. Будем скачивать заново.")

    # Обычное скачивание
    time.sleep(float(input_download_delay))
    url = f"{BASE_API_URL}/manga/{ranobe_name}/chapter?branch_id={priority_branch}&number={number}&volume={volume}"

    headers = {
        "Origin": "https://ranobelib.me",
        "Referer": "https://ranobelib.me/",
        "Authorization": f"Bearer {config.token}",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Host": HOST,
        "Sec-Gpc": "1",
        "Site-Id": "3",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
        ),
    }

    delays = _retry_delays()
    attempt = 0

    while True:
        try:
            attempt += 1
            if attempt > 1:
                log_func(f"\nПопытка {attempt}")

            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code} для главы {volume}-{number}")

            data = response.json().get("data")

            if isinstance(data.get("content"), str) and is_html(data.get("content")):
                content_type = "html"
                content = data.get("content")
            else:
                content_type = "doc"
                content = data.get("content").get("content")

            attachments = [
                Attachment(
                    id=item.get("id"),
                    name=item.get("name"),
                    url=item.get("url"),
                    extension=item.get("extension"),
                    filename=item.get("filename"),
                    width=item.get("width"),
                    height=item.get("height"),
                )
                for item in data.get("attachments") or []
            ]

            chapter = ChapterData(
                id=data.get("id"),
                number=data.get("number"),
                volume=data.get("volume"),
                type=content_type,
                content=content,
                attachments=attachments,
            )

            # Сохраняем в кеш
            try:
                if save_to_cache:
                    cache_chapter(cache_path, chapter, attachments)
            except Exception as e:
                log_func(f"Ошибка при сохранении кеша: {e}")

            return chapter

        except (RequestException, Timeout, Exception) as exc:
            delay = next(delays)
            log_func(f"\n[{attempt}] Ошибка: {exc}. Повтор через {delay} сек")
            time.sleep(delay)
