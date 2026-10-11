import tomllib
from pathlib import Path

from pista import version


def test_version_comes_from_pyproject():
    data = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text("utf-8"))
    assert version() == data["project"]["version"]
