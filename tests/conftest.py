import pytest

from pista.core.breaker import BREAKER


@pytest.fixture(autouse=True)
def _fresh_breaker():
    """The YouTube breaker is process-wide; a test that trips it must not pause the next one."""
    BREAKER.resume()
    BREAKER.record_success()
    yield
    BREAKER.resume()
    BREAKER.record_success()
