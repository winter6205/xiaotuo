import pytest

from xiaotuo import ratelimit
from xiaotuo.config import settings
from xiaotuo.errors import ApiError


def test_multiplier_scales_limit(monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "ratelimit_multiplier", 2)
    for _ in range(10):
        ratelimit.hit("register_ip", "1.2.3.4")
    with pytest.raises(ApiError):
        ratelimit.hit("register_ip", "1.2.3.4")
    ratelimit.reset()
