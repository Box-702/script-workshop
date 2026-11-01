# =====================================================================
# assets.py —— 资产键的解析层：**一切都是 id，名字只是显示用的别名**
#
# 解决什么
# --------
# 角色与场景的五份资产（外貌锚 / 环境锚 / 定妆图 / 音色 / 性别）过去全部以
# **中文名**做键：
#
#     character_appearances: {"孔乙己": "……"}
#     reference_images:      {"孔乙己": "https://…"}
#     voice_casting:         {"孔乙己": "male-qn-badao"}
#
# 名字是 LLM 随手写的、也是用户随时会改的。改一次名（「酒客甲」→「短衣帮甲」），
# 五份锚点同时失联——而且**不报错**：查不到就当没有，定妆图不出、音色回落到
# 推断、外貌锚消失。这是「长篇必跑偏」的根源，比任何模型能力问题都严重。
#
# 现在的约定
# ----------
# · **存储用 id**：`{"char_004": …}` / `{"loc_001": …}`。
# · **模型用名字**：美术指导照旧按名字写（LLM 写 id 的准确率很低），
#   代码在落库前把名字映射成 id（`rekey`）。格式由代码保证，不指望模型。
# · **读取两种都认**：老项目里存的是名字键，`lookup()` 先按 id 查、再按名字查，
#   所以不需要一次性迁移数据；下次写入时自然变成 id 键。
#
# 一句话：**名字是人的语言，id 是数据的主键。两者在边界处转换一次，中间全程用 id。**
# =====================================================================

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import Script

# 五份按实体索引的资产（键都应该是实体 id）。
CHAR_APPEARANCES = "character_appearances"
ENV_DESCRIPTIONS = "environment_descriptions"
REFERENCE_IMAGES = "reference_images"
VOICE_CASTING = "voice_casting"
CHARACTER_GENDERS = "character_genders"

ASSET_KEYS = (
    CHAR_APPEARANCES,
    ENV_DESCRIPTIONS,
    REFERENCE_IMAGES,
    VOICE_CASTING,
    CHARACTER_GENDERS,
)

# 名字匹配时忽略的字符（标点、空白、括号——「酒客甲」「酒客 甲」不该算两个人）。
_NOISE = set(" \t\r\n　·•-—_()（）[]【】「」、，。.·:：")


def norm(text: object) -> str:
    """名字归一化：只留实义字符，用于「同一个人的两种写法」比对。"""
    return "".join(ch for ch in str(text or "") if ch not in _NOISE)


@dataclass
class Index:
    """剧本里的实体索引：id ↔ 名字的双向查找。"""

    by_id: dict[str, str] = field(default_factory=dict)      # id -> 显示名
    by_name: dict[str, str] = field(default_factory=dict)    # 归一化名字 -> id
    ambiguous: set[str] = field(default_factory=set)         # 重名的名字（不做映射）

    def resolve(self, key: object) -> str | None:
        """把「id 或名字」解析成 id；解析不出来返回 None。

        重名的名字**不猜**——猜错等于把 A 的定妆图贴到 B 脸上，比没有更糟。
        """
        k = str(key or "").strip()
        if not k:
            return None
        if k in self.by_id:
            return k
        n = norm(k)
        if n in self.ambiguous:
            return None
        return self.by_name.get(n)

    def display(self, entity_id: str) -> str:
        return self.by_id.get(entity_id, entity_id)


def build_index(script: Script | None) -> Index:
    """从剧本建索引（角色 + 地点）。

    角色与地点共用一张表是安全的：它们的 id 前缀不同（`char_` / `loc_`），
    而名字重名的情况（角色叫「酒店」）极少，且重名会被标成 ambiguous 不参与映射。
    """
    idx = Index()
    if script is None:
        return idx

    def _add(entity_id: str, name: str) -> None:
        if not entity_id:
            return
        idx.by_id[entity_id] = name or entity_id
        n = norm(name)
        if not n:
            return
        if n in idx.by_name and idx.by_name[n] != entity_id:
            idx.ambiguous.add(n)
            return
        idx.by_name[n] = entity_id

    for c in script.characters or []:
        _add(c.id, c.name)
    for loc in script.locations or []:
        _add(loc.id, loc.name)
    # 重名的名字从映射表里删掉，避免 resolve 撞运气。
    for n in idx.ambiguous:
        idx.by_name.pop(n, None)
    return idx


def rekey(mapping: dict[str, str] | None, index: Index) -> dict[str, str]:
    """把「名字键」的资产表规整成「id 键」。

    幂等：已经是 id 键的原样保留；解析不出来的键（剧本里删掉的角色、
    模型写错的别名）**原样留着**——它们是用户的数据，不该因为对不上就丢。

    冲突处理：id 键优先于名字键（前者更可信，是代码写的；后者是模型写的）。
    """
    if not mapping:
        return {}
    out: dict[str, str] = {}
    # 先放 id 键
    for k, v in mapping.items():
        if str(k) in index.by_id:
            out[str(k)] = v
    # 再放名字键（不覆盖已存在的 id 键）
    for k, v in mapping.items():
        if str(k) in index.by_id:
            continue
        resolved = index.resolve(k)
        out.setdefault(resolved or str(k), v)
    return out


def normalize_style(style: dict | None, script: Script | None) -> dict:
    """把整个 video_style 里的五份资产表规整成 id 键（返回新 dict，不改入参）。

    这是「读的一次性入口」：调用方拿到之后可以放心全程按 id 取值。
    """
    out = dict(style or {})
    idx = build_index(script)
    for key in ASSET_KEYS:
        if key in out:
            out[key] = rekey(out.get(key) or {}, idx)
    return out


def lookup(mapping: dict[str, str] | None, entity_id: str, index: Index) -> str:
    """读一份资产：先按 id 查，再按显示名查（兼容老数据），都没有返回空串。"""
    if not mapping:
        return ""
    hit = mapping.get(entity_id)
    if hit:
        return str(hit)
    name = index.display(entity_id)
    if name and name in mapping:
        return str(mapping[name])
    return ""


def as_name_map(mapping: dict[str, str] | None, index: Index) -> dict[str, str]:
    """把资产表转成「显示名 → 值」，供**拼提示词**用。

    提示词里必须写「孔乙己：四十岁上下……」而不是「char_004：……」——
    视频模型不认识我们的内部 id。id 只在存储与逻辑里流转。
    """
    if not mapping:
        return {}
    out: dict[str, str] = {}
    for k, v in mapping.items():
        ent = index.resolve(k) or str(k)
        out[index.display(ent)] = str(v)
    return out
