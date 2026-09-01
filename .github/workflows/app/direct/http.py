from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import requests


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    etag: str | None
    last_modified: str | None
    content_hash: str
    not_modified: bool = False


class RobotsAwareClient:
    def __init__(self, timeout: int = 15, min_host_interval: float = 2.0, user_agent: str = "MunicipalPromotionSearch/6.0"):
        self.timeout = timeout
        self.min_host_interval = min_host_interval
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "ja,en;q=0.5"})
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser] = {}

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            rp = RobotFileParser(); rp.set_url(origin + "/robots.txt")
            try:
                response = self.session.get(origin + "/robots.txt", timeout=self.timeout)
                rp.parse(response.text.splitlines() if response.status_code == 200 else [])
            except Exception:
                rp.parse([])
            self._robots[origin] = rp
        return self._robots[origin].can_fetch(self.user_agent, url)

    def fetch(self, url: str, etag: str | None = None, last_modified: str | None = None) -> FetchResult:
        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        host = urlparse(url).netloc.lower()
        wait = self.min_host_interval - (time.monotonic() - self._last.get(host, 0.0))
        if wait > 0: time.sleep(wait)
        headers = {}
        if etag: headers["If-None-Match"] = etag
        if last_modified: headers["If-Modified-Since"] = last_modified
        response = self.session.get(url, timeout=self.timeout, headers=headers)
        self._last[host] = time.monotonic()
        if response.status_code == 304:
            return FetchResult(url, 304, "", etag, last_modified, "", True)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        text = response.text
        return FetchResult(url, response.status_code, text, response.headers.get("ETag"), response.headers.get("Last-Modified"), hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest())
