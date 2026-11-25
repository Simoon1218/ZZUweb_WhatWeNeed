import os
import secrets
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    port: int = int(os.getenv("PORT", "8000"))
    session_secret: str = os.getenv("SESSION_SECRET") or secrets.token_hex(32)
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_HOURS", "24")) * 3600
    max_sessions: int = int(os.getenv("MAX_SESSIONS", "1000"))
    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT", "15"))
    upstream_proxy: str = os.getenv("UPSTREAM_PROXY", "").strip()
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "auto").strip().lower() == "true"
    cookie_name: str = "zzu_web_sid"

    @property
    def proxies(self) -> dict[str, str] | None:
        if not self.upstream_proxy:
            return None
        return {
            "http": self.upstream_proxy,
            "https": self.upstream_proxy,
        }


settings = Settings()
