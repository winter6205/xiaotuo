import pytest

from app import ratelimit
from app.config import settings
from app.errors import ApiError


def test_multiplier_scales_limit(monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "ratelimit_multiplier", 2)
    for _ in range(10):
        ratelimit.hit("register_ip", "1.2.3.4")
    with pytest.raises(ApiError):
        ratelimit.hit("register_ip", "1.2.3.4")
    ratelimit.reset()
