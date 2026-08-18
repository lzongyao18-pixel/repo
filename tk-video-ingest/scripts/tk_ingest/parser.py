from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .errors import InvalidInputError
from .security import sanitize_category


_URL = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
_DIRECT_VIDEO_ID = re.compile(r"/(?:video|v)/(\d{8,})")
_ALLOWED_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}


@dataclass(frozen=True, slots=True)
class IngestRequest:
    url: str
    category: str


def validate_tiktok_url(url: str) -> str:
    cleaned = url.rstrip(".,;，。；）)]}")
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (host in _ALLOWED_HOSTS or host.endswith(".tiktok.com")):
        raise InvalidInputError("只接受 TikTok 视频链接。")
    return cleaned


def extract_video_id(url: str) -> str | None:
    match = _DIRECT_VIDEO_ID.search(urlparse(url).path)
    return match.group(1) if match else None


def parse_instruction(text: str, *, default_category: str = "待分类") -> IngestRequest:
    urls = _URL.findall(text)
    if len(urls) != 1:
        raise InvalidInputError("V1 每次必须且只能提供一个 TikTok 链接。")
    url = validate_tiktok_url(urls[0])
    prefix = text[: text.find(url)].strip()
    category = default_category
    match = re.search(r"收录到\s*[:：]\s*(.+)$", prefix)
    if match:
        category = match.group(1).strip()
    elif "收录" not in prefix:
        raise InvalidInputError("请使用“收录 <链接>”或“收录到：分类 <链接>”。")
    return IngestRequest(url=url, category=sanitize_category(category, default=default_category))
