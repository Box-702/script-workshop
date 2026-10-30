# =====================================================================
# test_keys.py —— 多 key 轮换（app/keys.py + 视频/配音接入）
#
# 覆盖三类风险：
#   1. 误判：参数错误（400/2013）绝不能被当成 key 失效，否则一次笔误就把
#      能用的 key 全判死、还冷却十分钟；
#   2. 漏判：402 余额不足 / 401 鉴权失败必须换 key 重试（这是本功能的意义）；
#   3. 串号：视频任务属于提交它的那个账号，轮换后查询必须回到同一把 key。
# =====================================================================

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.keys import (
    KeyRing,
    key_failure,
    mask,
    merge_keys,
    minimax_keys,
    reset_rings,
    ring_for,
    split_keys,
)

# ---------------- 纯函数层 ----------------


def test_split_keys_去重保序且支持多种分隔符():
    assert split_keys("a,b;c\nd  e") == ["a", "b", "c", "d", "e"]
    assert split_keys(" a , a ,b ") == ["a", "b"]
    assert split_keys(["x", "y", "x"]) == ["x", "y"]
    assert split_keys("") == []
    assert split_keys(None) == []


def test_merge_keys_先出现的优先():
    assert merge_keys("a", "b,a", ["c"]) == ["a", "b", "c"]


def test_key_failure_只认_key_级错误():
    # key 级：该换 key
    assert key_failure(401, {}) is True
    assert key_failure(402, {"error": {"message": "insufficient balance (1008)"}}) is True
    assert key_failure(200, {"base_resp": {"status_code": 1004}}) is True
    # 非 key 级：换 key 也没用，不能误判
    assert key_failure(400, {"base_resp": {"status_code": 2013}}) is False
    assert key_failure(200, {"task_id": "123"}) is False
    assert key_failure(429, {"error": "rate limit"}) is False
    assert key_failure(400, {"msg": "invalid 11008 format"}) is False


def test_mask_不泄露完整_key():
    long_key = "sk-" + "x" * 40
    shown = mask(long_key)
    assert long_key not in shown
    assert shown.startswith("sk-")
    assert mask("") == "(空)"


def test_keyring_坏_key_排到最后_但仍作为兜底():
    ring = KeyRing(["k1", "k2"], cooldown=600)
    assert ring.candidates() == ["k1", "k2"]
    ring.mark_bad("k1", "余额不足")
    assert ring.candidates() == ["k2", "k1"]  # 健康优先，冷却中的垫后
    ring.mark_ok("k1")
    assert ring.candidates() == ["k1", "k2"]


def test_keyring_冷却到期自动复活():
    ring = KeyRing(["k1"], cooldown=0)
    ring.mark_bad("k1", "余额不足")
    assert ring.candidates() == ["k1"]  # cooldown=0：立即恢复
    assert ring.snapshot()[0]["healthy"] is True


def test_keyring_空配置不炸():
    ring = KeyRing([])
    assert ring.pick() == ""
    assert ring.candidates() == []


def test_ring_for_键变了就重建():
    reset_rings()
    a = ring_for("demo", "k1")
    b = ring_for("demo", "k1")
    assert a is b  # 同一份配置复用同一个环（冷却状态共享）
    c = ring_for("demo", "k1,k2")
    assert c is not a
    assert c.ordered() == ["k1", "k2"]


def test_minimax_keys_合并显式与备用(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "env-primary")
    monkeypatch.setenv("MINIMAX_API_KEY_FALLBACKS", "env-fb1,env-fb2")
    monkeypatch.setenv("MINIMAX_API_KEYS", "env-primary,env-extra")
    assert minimax_keys("explicit") == [
        "explicit",
        "env-primary",
        "env-extra",
        "env-fb1",
        "env-fb2",
    ]


# ---------------- 视频 Provider 的轮换（打桩 httpx） ----------------


class _FakeAsyncClient:
    """只实现被测代码用到的那几个方法；记录每次请求用的 key。"""

    calls: list[tuple[str, str]] = []
    handler = staticmethod(lambda method, url, body: None)

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append((url, _key_of(headers)))
        return self.handler("POST", url, json)

    async def get(self, url, headers=None):
        self.calls.append((url, _key_of(headers)))
        return self.handler("GET", url, None)


def _key_of(headers) -> str:
    return (headers or {}).get("Authorization", "").removeprefix("Bearer ")


def _resp(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(status, json=payload, request=httpx.Request("POST", "https://api.minimax.cn/"))


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """清环境变量与全局状态，避免测试之间互相污染。"""
    from app.video.providers.minimax import MiniMaxProvider

    for name in ("MINIMAX_API_KEY", "MINIMAX_API_KEYS", "MINIMAX_API_KEY_FALLBACKS", "KEY_COOLDOWN_SEC"):
        monkeypatch.delenv(name, raising=False)
    reset_rings()
    _FakeAsyncClient.calls = []
    MiniMaxProvider._TASK_KEYS.clear()
    yield
    reset_rings()
    MiniMaxProvider._TASK_KEYS.clear()


def _provider(monkeypatch, handler, keys: str):
    """按 "第一把,备用1,备用2" 造一个 Provider：显式传第一把，其余进 .env 备用位。"""
    from app.video.providers import minimax as mm

    _FakeAsyncClient.handler = staticmethod(handler)
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(mm.httpx, "AsyncClient", _FakeAsyncClient)

    first, *rest = [k.strip() for k in keys.split(",") if k.strip()]
    if rest:
        monkeypatch.setenv("MINIMAX_API_KEY_FALLBACKS", ",".join(rest))
    return mm.MiniMaxProvider(api_key=first)


def test_视频提交_主_key_欠费自动换备用(monkeypatch):
    def handler(method, url, body):
        key = _FakeAsyncClient.calls[-1][1]
        if key == "bad-key":
            return _resp(
                402,
                {"type": "error", "error": {"type": "insufficient_balance_error",
                                            "message": "insufficient balance (1008)"}},
            )
        return _resp(200, {"task_id": "task-1"})

    provider = _provider(monkeypatch, handler, "bad-key,good-key")
    result = asyncio.run(provider.create_job("测试提示词", None))

    assert result.external_task_id == "task-1"
    # 先用主 key，被拒后换备用 key
    assert [c[1] for c in _FakeAsyncClient.calls] == ["bad-key", "good-key"]
    # 任务记住「提交它的那把 key」，后续查询要回到同一账号
    assert provider._TASK_KEYS["task-1"] == "good-key"

    # 坏 key 进冷却：下一次请求不再先撞它
    _FakeAsyncClient.calls = []
    asyncio.run(provider.create_job("第二条", None))
    assert [c[1] for c in _FakeAsyncClient.calls] == ["good-key"]


def test_视频提交_参数错误不换_key_也不冷却(monkeypatch):
    def handler(method, url, body):
        return _resp(
            400,
            {"type": "error", "error": {"type": "bad_request_error", "message": "invalid params (2013)"}},
        )

    provider = _provider(monkeypatch, handler, "key-a,key-b")
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(provider.create_job("测试", None))

    # 只打了第一把：参数错换 key 没用，不该继续试、也不该判死
    assert [c[1] for c in _FakeAsyncClient.calls] == ["key-a"]
    assert provider._ring().snapshot()[0]["healthy"] is True


def test_视频提交_全部_key_失效时报清楚账(monkeypatch):
    def handler(method, url, body):
        return _resp(
            401,
            {"type": "error", "error": {"type": "authorized_error", "message": "login fail (1004)"}},
        )

    provider = _provider(monkeypatch, handler, "key-a,key-b")
    with pytest.raises(RuntimeError) as err:
        asyncio.run(provider.create_job("测试", None))

    message = str(err.value)
    assert "所有 key 都不可用" in message
    assert "1004" in message          # 报清楚账：哪一把、为什么
    assert len(_FakeAsyncClient.calls) == 2  # 两把都试过
    assert "key-a," not in message    # 不泄露完整 key


def test_查询任务_用提交时那把_key(monkeypatch):
    """跨账号轮换后，用错账号查会拿到 2013；要能回到正确的 key。"""

    def handler(method, url, body):
        key = _FakeAsyncClient.calls[-1][1]
        if key == "account-a":
            return _resp(200, {"base_resp": {"status_code": 2013, "status_msg": "invalid task_id"}})
        return _resp(
            200,
            {"task": {"id": "task-9", "status": "succeeded", "content": {"url": "https://cdn/x.mp4"}}},
        )

    provider = _provider(monkeypatch, handler, "account-a,account-b")
    # 模拟：任务由 account-b 提交（真实场景是上一轮轮换后提交的）
    provider._remember("task-9", "account-b")

    status = asyncio.run(provider.poll_job("task-9"))
    assert status.status == "succeeded"
    assert status.video_url == "https://cdn/x.mp4"
    # 绑定的 key 优先：一次命中，不会去撞 account-a
    assert [c[1] for c in _FakeAsyncClient.calls] == ["account-b"]


def test_查询任务_2013_不判_key_失效(monkeypatch):
    def handler(method, url, body):
        key = _FakeAsyncClient.calls[-1][1]
        if key == "account-a":
            return _resp(200, {"base_resp": {"status_code": 2013, "status_msg": "invalid task_id"}})
        return _resp(200, {"task": {"id": "task-9", "status": "running"}})

    provider = _provider(monkeypatch, handler, "account-a,account-b")
    status = asyncio.run(provider.poll_job("task-9"))

    assert status.status == "generating"
    # account-a 只是「查不到这个任务」，key 本身是好的，不能冷却
    assert all(s["healthy"] for s in provider._ring().snapshot())


# ---------------- 配音的轮换 ----------------


def test_配音_主_key_欠费自动换备用(monkeypatch):
    from app.llm import tts as tts_mod
    from app.llm.base import ModelConfig

    calls: list[str] = []

    class _FakeClient:
        def __init__(self, *a, **kw) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, headers=None, json=None):
            key = _key_of(headers)
            calls.append(key)
            if key == "bad":
                return httpx.Response(
                    402,
                    json={"base_resp": {"status": 1008, "status_msg": "insufficient balance"}},
                    request=httpx.Request("POST", url),
                )
            return httpx.Response(
                200,
                json={"data": {"audio": "494433"}, "base_resp": {"status": 0}},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(tts_mod.httpx, "Client", _FakeClient)
    monkeypatch.setenv("MINIMAX_API_KEY_FALLBACKS", "good")

    client = tts_mod.MiniMaxTTSClient(
        ModelConfig(provider="minimax", model="speech-02-hd", api_key="bad", base_url="https://api.minimax.cn")
    )
    audio = client.synthesize("台词")

    assert audio == b"ID3"
    assert calls == ["bad", "good"]


def test_配音响应解析_无音频时给清楚错误():
    from app.llm.tts import MiniMaxTTSClient

    with pytest.raises(RuntimeError, match="没有音频"):
        MiniMaxTTSClient._parse_audio({"data": {}, "base_resp": {"status": 0}})
    with pytest.raises(RuntimeError, match="JSON"):
        MiniMaxTTSClient._parse_audio("<html>502</html>")
