import io
import time

from PIL import Image
import PIL
import cloudscraper
import requests

from src.config import config
from src.model import Attachment, ChapterData, ChapterMeta
from src.utils import is_html, is_url


def get_base_api_url() -> str:
    response = requests.get(
        f"https://gist.githubusercontent.com/DustGalaxy/958d8a9fe76d7253d1511d99d180d1c5.txt?nocache={int(time.time())}"
    )
    if response.status_code == 200:
        return str(response.content.decode("utf-8")).strip()


BASE_API_URL = get_base_api_url()


def get_latest_release(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    response = requests.get(url)
    if response.ok:
        data = response.json()
        return data["tag_name"]
    else:
        raise Exception(f"Ошибка запроса: {response.status_code} - {response.text}")


def get_branchs(ranobe_id: str) -> dict:
    url = f"{BASE_API_URL}/branches/{ranobe_id}?team_defaults=1"

    response = requests.get(url)

    if response.status_code != 200:
        return None

    return response.json().get("data")


def get_ranobe_data(name: str) -> dict:
    url_base = f"{BASE_API_URL}/manga/{name}?"
    url = url_base + "&".join([
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
    ])
    response = requests.get(
        url,
        headers={
            "Origin": "https://ranobelib.me",
            "Referer": "https://ranobelib.me/",
            "Authorization": f"Bearer {config.token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        },
    )
    if response.status_code != 200:
        return None

    return response.json().get("data")


def get_chapters_data(name: str) -> list[ChapterMeta]:
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


def get_image_content(url: str, format: str) -> bytes:
    try:
        scraper = cloudscraper.create_scraper(
            delay=15,
            browser={"browser": "firefox", "platform": "windows", "mobile": False},
        )
        if format.upper() == "JPG":
            format = "JPEG"

        if not is_url(url):
            return b""

        for _ in range(3):
            try:
                # Получаем картинку по ссылке
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


def get_chapter(ranobe_name: str, priority_branch: str, number: int, volume: int) -> ChapterData:
    url = f"{BASE_API_URL}/manga/{ranobe_name}/chapter?branch_id={priority_branch}&number={number}&volume={volume}"
    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {config.token}",
        },
    )
    if response.status_code != 200:
        raise Exception(f"Ошибка при получении главы {volume} - {number}. Пропускаем главу {volume} - {number}")

    else:
        data = response.json().get("data")

        if isinstance(data.get("content"), str) and is_html(data.get("content")):
            type = "html"
            content = data.get("content")
        else:
            type = "doc"
            content = data.get("content").get("content")

        attachments = []
        if len(data.get("attachments")):
            for item in data.get("attachments"):
                attachments.append(
                    Attachment(
                        id=item.get("id"),
                        name=item.get("name"),
                        url=item.get("url"),
                        extension=item.get("extension"),
                        filename=item.get("filename"),
                        width=item.get("width"),
                        height=item.get("height"),
                    )
                )

        return ChapterData(
            id=data.get("id"),
            number=data.get("number"),
            volume=data.get("volume"),
            type=type,
            content=content,
            attachments=attachments,
        )
