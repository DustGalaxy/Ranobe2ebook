import re
import base64
from urllib.parse import urlparse

from jwt import decode, DecodeError
from FB2 import Author


def is_url(url) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def set_authors(authors) -> list[Author]:
    result_list = []
    for author in authors:
        result_list.append(
            Author(
                firstName=author.get("name"),
            )
        )

    return result_list


def is_jwt(token) -> bool:
    parts = token.split(".")
    if len(parts) != 3:
        return False

    try:
        base64.urlsafe_b64decode(parts[0] + "==").decode("utf-8")
        base64.urlsafe_b64decode(parts[1] + "==").decode("utf-8")
    except (ValueError, base64.binascii.Error):
        return False

    try:
        decode(token, options={"verify_signature": False})
    except DecodeError:
        return False

    return True


def is_html(text) -> bool:
    html_tag_pattern = re.compile(r"<(\/?[^>]+)>")

    tags = html_tag_pattern.findall(text)

    if not tags:
        return False

    known_html_tags = {
        "html",
        "head",
        "body",
        "title",
        "meta",
        "link",
        "script",
        "style",
        "div",
        "span",
        "p",
        "a",
        "img",
        "ul",
        "ol",
        "li",
        "table",
        "tr",
        "td",
        "th",
        "form",
        "input",
        "button",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "br",
        "hr",
    }

    for tag in tags:
        tag_name = tag.split()[0].strip("/")
        if tag_name.lower() in known_html_tags:
            return True

    return False


def is_valid_url(url) -> bool:
    parsed = urlparse(url)

    if all([parsed.scheme == "https", parsed.netloc == "ranobelib.me", parsed.path]):
        pattern = re.compile(r"^/ru/book/.*")
        return bool(pattern.match(parsed.path))

    return False

def html_text_formatting(mark_type) -> str:
    match mark_type:
        case "bold":
            return "b"
        case "italic":
            return "i"
        case "underline":
            return "ins"
        case "strike":
            return "del"
        case _:
            return -1