import os
import sys
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
os.environ.setdefault("STATE_KEY", "unit-test-state-key-123456")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from ghbot.core.db import Database  # noqa: E402


@pytest_asyncio.fixture
async def db(tmp_path):
    d = await Database(tmp_path / "t.db").open()
    yield d
    await d.close()
