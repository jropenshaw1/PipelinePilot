"""Test isolation for ADR-014: no test touches the real lock file or the
real pipelinepilot.config (whose archive_root could point at real folders)."""
import importlib

import pytest

import config
import filesystem


@pytest.fixture(autouse=True)
def _isolate_lock_and_config(tmp_path_factory, monkeypatch):
    scratch = tmp_path_factory.mktemp("pipi_local")
    monkeypatch.setattr(filesystem, "lock_dir", lambda: scratch / "PipelinePilot")
    monkeypatch.setattr(config, "CONFIG_PATH", scratch / "no_such.config")


@pytest.fixture
def api_error():
    """Builds a real anthropic SDK API error, e.g. api_error("NotFoundError", 404, "gone").
    The SDK's own HTTP library builds the request and response: httpx2 from SDK 1.0,
    httpx before it. Skips the test where the SDK or that library is not installed."""
    anthropic = pytest.importorskip("anthropic")
    for name in ("httpx2", "httpx"):
        try:
            http = importlib.import_module(name)
            break
        except ImportError:
            continue
    else:
        pytest.skip("the anthropic SDK's HTTP library (httpx2 or httpx) is not installed")

    def make(cls_name, status, text):
        req = http.Request("POST", "https://api.anthropic.com/v1/messages")
        return getattr(anthropic, cls_name)(text, response=http.Response(status, request=req), body=None)
    return make
