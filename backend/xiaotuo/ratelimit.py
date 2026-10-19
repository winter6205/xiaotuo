"""单实例进程内滑动窗口限流（扩容到多实例时改用 PostgreSQL / Redis）。"""
import math
import time
from collections import defaultdict, deque

from xiaotuo.config import settings
from xiaotuo.errors import ApiError

# openapi RateLimited 默认值；无默认值的接口取保守值（见 README）
RULES = {
    "login_ip": (10, 60), "login_email": (5, 900),
    "register_ip": (5, 3600),
    "reset_ip": (5, 3600), "reset_email": (3, 3600),
    "reset_confirm_ip": (10, 3600),
    "events_user": (120, 60),
    "import_user": (30, 60),
    "progress_reset_user": (10, 3600),
}

_hits: dict[str, deque] = defaultdict(deque)


def reset() -> None:
    _hits.clear()


def hit(rule: str, key: str) -> None:
    limit, window = RULES[rule]
    limit *= max(1, settings.ratelimit_multiplier)
    now = time.monotonic()
    q = _hits[f"{rule}:{key}"]
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= limit:
        retry = max(1, math.ceil(q[0] + window - now))
        raise ApiError(429, "rate_limited", f"尝试太频繁，请 {retry} 秒后再试",
                       {"retry_after": retry}, {"Retry-After": str(retry)})
    q.append(now)
