import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field

from .config import settings


@dataclass
class UserSession:
    session_id: str
    account: str
    demo_mode: bool = False
    user_token: str = ""
    jw_token: str = ""
    jsession_id: str = ""
    tid: str = ""
    refresh_token: str = ""
    ecard_access_token: str = ""
    ecard_token_updated_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    # Used only in demo mode to simulate card balance changes
    demo_card_balance: float = 128.60
    demo_electric_balance: float = 46.50
    demo_transfers: list[dict] = field(default_factory=list)


class SessionStore:
    """Thread-safe in-memory session store with TTL eviction.

    Plaintext user passwords and campus card passwords are NEVER stored.
    """

    def __init__(self, ttl_seconds: int, max_sessions: int) -> None:
        self._ttl = ttl_seconds
        self._max_sessions = max_sessions
        self._sessions: dict[str, UserSession] = {}
        self._lock = threading.RLock()

    def _sign(self, session_id: str) -> str:
        sig = hmac.new(
            settings.session_secret.encode("utf-8"),
            session_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:24]
        return f"{session_id}.{sig}"

    def _verify(self, signed_value: str | None) -> str | None:
        if not signed_value or "." not in signed_value:
            return None
        session_id, sig = signed_value.rsplit(".", 1)
        expected = hmac.new(
            settings.session_secret.encode("utf-8"),
            session_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected):
            return None
        return session_id

    def _cleanup_locked(self, now: float) -> None:
        expired = [
            sid
            for sid, sess in self._sessions.items()
            if now - sess.last_accessed_at > self._ttl
        ]
        for sid in expired:
            del self._sessions[sid]

        if len(self._sessions) >= self._max_sessions:
            oldest = sorted(
                self._sessions.items(), key=lambda kv: kv[1].last_accessed_at
            )
            to_drop = len(self._sessions) - self._max_sessions + 1
            for sid, _ in oldest[:to_drop]:
                del self._sessions[sid]

    def create(
        self,
        account: str,
        user_token: str = "",
        demo_mode: bool = False,
    ) -> tuple[UserSession, str]:
        now = time.time()
        session_id = secrets.token_urlsafe(24)
        sess = UserSession(
            session_id=session_id,
            account=account,
            user_token=user_token,
            demo_mode=demo_mode,
            created_at=now,
            last_accessed_at=now,
        )
        with self._lock:
            self._cleanup_locked(now)
            self._sessions[session_id] = sess
        return sess, self._sign(session_id)

    def get(self, signed_cookie: str | None) -> UserSession | None:
        session_id = self._verify(signed_cookie)
        if not session_id:
            return None
        now = time.time()
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return None
            if now - sess.last_accessed_at > self._ttl:
                del self._sessions[session_id]
                return None
            sess.last_accessed_at = now
            return sess

    def delete(self, signed_cookie: str | None) -> None:
        session_id = self._verify(signed_cookie)
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)


session_store = SessionStore(
    ttl_seconds=settings.session_ttl_seconds,
    max_sessions=settings.max_sessions,
)
