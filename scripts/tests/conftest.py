import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def render_root_config():
    from render_root_openclaw_config import build_config

    return build_config()
