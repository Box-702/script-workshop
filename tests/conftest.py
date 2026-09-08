# =====================================================================
# conftest.py —— 测试公共夹具
#
# 用 SQLite + 内存 checkpointer 跑测试，无需外部服务。
# =====================================================================

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

# 保证默认走内存 checkpoint，避免测试污染全局单例。
os.environ.setdefault("CHECKPOINTER", "memory")
os.environ.setdefault("OPENAI_API_KEY", "")

from app.config import Settings  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.store import Store  # noqa: E402


@pytest.fixture()
def tmp_db_path(tmp_path_factory: pytest.TempPathFactory):
    d = Path(__file__).resolve().parent.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"test_{os.getpid()}_{time.time_ns()}.db"
    yield path.as_posix()
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        DATABASE_URL="sqlite:///./data/_unused.db",
        CHECKPOINTER="memory",
        OPENAI_API_KEY="",
        ZHIPUAI_API_KEY="",
        DEEPSEEK_API_KEY="",
        CHECKPOINT_DSN="",
    )


@pytest.fixture()
def store(tmp_db_path) -> Store:
    db_url = f"sqlite:///{tmp_db_path}"
    s = Store(db_url)
    yield s
    try:
        s.engine.dispose()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture()
def llm(settings) -> LLM:
    return LLM(settings)


@pytest.fixture()
def sample_text() -> str:
    return (
        '凌晨三点，滨江路的路灯在雨里像一团化不开的黄。林然把车停在旧楼前，'
        '熄了火，雨水顺着挡风玻璃往下淌。\n'
        '阿姐坐在里头的一把折叠椅上，说："你终于来了。"林然没答话。\n'
        '角落里站着一个穿红雨衣的男人，把一张照片按在桌上，照片上是失火前夜的'
        '旧货市场。'
    )
