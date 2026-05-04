def get_headers(hostname: str, token: str) -> dict[str, str]:
    return {
        "Priority": "u=0",
        "Origin": "https://ranobelib.me",
        "Referer": "https://ranobelib.me/",
        "Authorization": f"Bearer {token}",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Host": hostname,
        "Sec-Gpc": "1",
        "Site-Id": "3",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    }


def get_image_headers(is_cover: bool = False) -> dict[str, str]:
    return (
        {
            "Host": "ranobelib.me",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
            "Accept": "image/avif,image/jxl,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": "https://ranobelib.me/",
            "Sec-GPC": "1",
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "Priority": "u=5, i",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "trailers",
        }
        if not is_cover
        else {
            "Host": "cover.imglib.info",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
            "Accept": "image/avif,image/jxl,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": "https://ranobelib.me/",
            "Sec-Fetch-Storage-Access": "none",
            "Sec-GPC": "1",
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
            "Connection": "keep-alive",
        }
    )
