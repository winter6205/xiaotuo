from app.config import Settings


def test_port_defaults_to_13773(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    assert Settings(_env_file=None).port == 13773


def test_port_reads_env(monkeypatch):
    monkeypatch.setenv("PORT", "18080")
    assert Settings(_env_file=None).port == 18080
