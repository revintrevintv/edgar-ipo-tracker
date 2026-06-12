import time

import requests


class EdgarClient:
    """HTTP client for SEC EDGAR APIs.

    Enforces a User-Agent header (SEC requirement) and a conservative
    request rate to stay well under SEC's 10 req/s access limit.
    """

    EFTS_BASE = "https://efts.sec.gov"
    DATA_BASE = "https://data.sec.gov"
    WWW_BASE = "https://www.sec.gov"

    def __init__(self, user_agent: str, requests_per_second: float = 5.0):
        if not user_agent or "@" not in user_agent:
            raise ValueError(
                "user_agent must include contact info, e.g. 'Your Name your@email.com'"
            )
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        self._interval = 1.0 / requests_per_second
        self._last = 0.0

    def get(self, url: str, **kwargs) -> requests.Response:
        elapsed = time.monotonic() - self._last
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        resp = self._session.get(url, timeout=30, **kwargs)
        self._last = time.monotonic()
        resp.raise_for_status()
        return resp
