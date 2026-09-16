# =====================================================================
# knowledge.py —— 改编知识（纯内存，无 RAG）
#
# 提供三类知识，全部以内存数据结构 + 工具函数的形式存在：
#
#   1. 题材种子知识：按题材分类的剧情走向与写作手法（硬编码）；
#   2. 作者风格提取：从原文启发式提取的语言风格画像（规则引擎）；
#   3. 知识格式化：将上述知识格式化为 prompt 片段。
#
# 这些知识不再向量化存储，而是：
#   - 种子知识 → 按题材查字典，直接注入 prompt 或由 Agent 工具调用；
#   - 作者风格 → 项目创建时提取一次，存入项目 notes，Agent 可随时读取。
# =====================================================================

from __future__ import annotations

import json
import re
from typing import Any

from ..llm import LLM

# 知识种类。
KNOWLEDGE_KINDS: tuple[str, ...] = ("plot_direction", "technique", "author_style")

# 各知识种类的中文标签。
KIND_LABELS: dict[str, str] = {
    "plot_direction": "同类剧本的可能走向",
    "technique": "同类剧本的写作手法",
    "author_style": "当前作者的语言风格",
}


# ---------- 题材识别 ----------

_GENRE_KEYWORDS: dict[str, list[str]] = {
    "悬疑": ["悬疑", "推理", "破案", "侦探", "杀人", "失踪", "秘密", "谜", "真相", "案件", "调查", "阴谋", "证据", "凶手"],
    "逆袭": ["逆袭", "打脸", "翻身", "复仇", "崛起", "扮猪吃虎", "废柴", "系统", "碾压", "爽文"],
    "情感": ["爱情", "恋爱", "婚姻", "分手", "心动", "告白", "前任", "虐恋", "暗恋", "重逢", "心动"],
    "家庭": ["家庭", "亲情", "母亲", "父亲", "姐妹", "兄弟", "婆媳", "原生家庭", "和解", "血缘"],
    "都市": ["都市", "职场", "城市", "公司", "加班", "合租", "地铁", "写字楼", "白领", "生意"],
    "奇幻": ["玄幻", "修仙", "魔法", "异能", "穿越", "重生", "神魔", "冒险", "剑", "龙", "秘境"],
}
_DEFAULT_GENRE = "通用"


def detect_genres(raw_text: str, top: int = 2) -> list[str]:
    """按关键词粗判题材，返回命中分数最高的题材列表（至少含「通用」兜底）。"""
    text = (raw_text or "")[:6000]
    scored: list[tuple[int, str]] = []
    for genre, words in _GENRE_KEYWORDS.items():
        score = sum(text.count(w) for w in words)
        if score > 0:
            scored.append((score, genre))
    scored.sort(key=lambda x: x[0], reverse=True)
    genres = [g for _, g in scored[:top]]
    return genres or [_DEFAULT_GENRE]


# ---------- 同类剧本种子知识库 ----------

SEED_KNOWLEDGE: dict[str, dict[str, list[str]]] = {
    "悬疑": {
        "plot_direction": [
            "真相反转型：结尾推翻观众的默认推断（如：真正的幕后黑手是最早出现的边缘角色）。",
            "双线追凶型：明线是主角破案，暗线是主角自身秘密逐步暴露，两线在最后汇合。",
            "有限视角误导型：通过限缩主角所知信息制造错判，关键证据用细节物件埋线。",
            "情感悬疑型：案件与家庭/情感创伤绑定，破解谜题的同时完成人物的情感闭环。",
        ],
        "technique": [
            "用细节物件做钩子（照片、钥匙、旧物），在开头抛出、结尾回收，形成结构呼应。",
            "信息差叙事：让观众比主角先知道一点、又比真相少知道一点，保持张力。",
            "对白潜台词化：嫌疑人的台词表面应答、实际隐瞒，用答非所问制造疑点。",
            "冷开场 + 每场结尾留问号：用追问式结尾推动连续观看。",
        ],
    },
    "逆袭": {
        "plot_direction": [
            "扮猪吃虎型：主角刻意隐藏实力，在关键场合一次性亮牌打脸对手。",
            "系统成长型：主角获得成长机制，从被轻视到碾压，形成爽点阶梯。",
            "复仇回归型：多年后以新身份回到旧环境，逐层清算旧恩怨。",
            "踩点反转型：每次看似绝境都在结尾反转，让观众期待下一次打脸。",
        ],
        "technique": [
            "先抑后扬：开头充分刻画主角被轻视的处境，为后续打脸积蓄情绪势能。",
            "爽点前置：每 1-2 场安排一次小反转或身份揭示，保持高频刺激。",
            "配角脸谱化对比：用势利配角的夸张反应衬托主角反差，制造喜剧张力。",
            "身份悬念：主角真实身份作为长线钩子，分阶段揭示。",
        ],
    },
    "情感": {
        "plot_direction": [
            "错位重逢型：多年后重逢，误会与旧情交织，先虐后甜。",
            "极限拉扯型：两人互相试探、反复靠近又推开，情感张力靠误会与错过维持。",
            "双向救赎型：两个带着创伤的人互相治愈，结局完成情感闭环。",
            "现实抉择型：爱情面对现实压力（家庭/事业/阶层），结局做开放式选择。",
        ],
        "technique": [
            "用细节动作代替表白：递伞、留灯、改备注，情感藏在动作里比台词更有力。",
            "克制对白：越关键的话越不说出口，用沉默与欲言又止制造张力。",
            "意象贯穿：用一个贯穿全剧的意象（照片、车站、歌）承载两人关系变化。",
            "情绪节拍化：把心动/心碎拆成可见的行为节拍，而非直接叙述感受。",
        ],
    },
    "家庭": {
        "plot_direction": [
            "和解型：多年隔阂在一次事件中被打破，家人互相理解，完成情感回归。",
            "秘密揭晓型：家庭里隐藏的秘密（身世/债务/背叛）被揭开，关系重新洗牌。",
            "代际冲突型：新旧观念碰撞，最终以互相让步达成新的平衡。",
            "缺失回归型：缺席的家庭成员回归，打乱既有秩序后重建。",
        ],
        "technique": [
            "饭桌戏承载冲突：家庭矛盾在饭桌这样的日常场景中爆发，反差更强烈。",
            "物件承载记忆：老物件（旧照片、缝纫机、钥匙）作为亲情线索。",
            "台词留白：家人之间话少，重要感情用动作与停顿表达。",
            "多线交织：几个家庭成员各有一条小线，在核心事件上汇合。",
        ],
    },
    "都市": {
        "plot_direction": [
            "职场逆袭型：小人物在职场遭遇打压，凭借能力与关键机会翻盘。",
            "都市群像型：同一空间（写字楼/合租房）里多组人物故事交织。",
            "现实压力型：主角面对房贷、裁员、大城市孤独，做艰难选择。",
            "小人物高光型：平凡主角在某个瞬间做出不平凡的举动，获得认可。",
        ],
        "technique": [
            "空间即舞台：用写字楼、出租屋、地铁等公共空间承载人物关系变化。",
            "加班与烟火气对照：用深夜加班的冷与回家的一盏灯形成情绪对照。",
            "白描式细节：用办公桌上的细节（过期的便签、没吃完的外卖）刻画处境。",
            "克制现实主义：不强行圆满，关键处留白，让结局有现实余味。",
        ],
    },
    "奇幻": {
        "plot_direction": [
            "成长升级型：主角从弱到强，经历试炼、获得力量，最终面对大敌。",
            "宿命对抗型：主角被预言/宿命绑定，在反抗宿命的过程中找到自我。",
            "异界冒险型：主角进入异世界/秘境，收集伙伴与信物，逐步揭开世界真相。",
            "力量代价型：获得力量需要付出代价，力量与代价的拉锯成为核心冲突。",
        ],
        "technique": [
            "世界观信息渐进释放：不一次性说明，借人物对话与场景细节层层揭晓。",
            "战斗即性格：通过战斗方式展现人物性格（谨慎、莽撞、守护）。",
            "规则感设定：力量有明确规则与代价，让冲突可推理、可期待。",
            "凡人视角带入：用普通人的感受描写奇观，增强代入感。",
        ],
    },
    "通用": {
        "plot_direction": [
            "三幕推进型：建立目标 → 遭遇阻碍与升级 → 高潮解决，符合经典叙事。",
            "人物弧光型：故事围绕主角的内心转变展开，事件为转变服务。",
            "意外卷入型：主角因一次意外卷入核心冲突，被迫成长并主动选择。",
            "双线呼应型：现在线与回忆/副线呼应，主题在两条线中互相印证。",
        ],
        "technique": [
            "开场三要素：尽快交代人物目标、核心冲突与危险，前三拍建立钩子。",
            "每场一场一目的：每场只推进一个戏剧目标，避免过场戏稀释节奏。",
            "对白服务冲突：对白携带信息与潜台词，避免纯闲聊填充。",
            "结尾留余韵：高潮之后给一个安静收尾拍，让情绪落地。",
        ],
    },
}


def get_genre_conventions(genre: str) -> dict[str, list[str]]:
    """按题材获取种子知识（纯内存字典查询）。"""
    return SEED_KNOWLEDGE.get(genre, SEED_KNOWLEDGE[_DEFAULT_GENRE])


def get_all_genre_knowledge(genres: list[str]) -> dict[str, list[str]]:
    """合并多个题材的知识（去重）。"""
    merged: dict[str, set[str]] = {"plot_direction": set(), "technique": set()}
    for genre in genres:
        conv = get_genre_conventions(genre)
        for kind in ("plot_direction", "technique"):
            merged[kind].update(conv.get(kind, []))
    return {k: sorted(v) for k, v in merged.items()}


def format_genre_knowledge(genres: list[str]) -> str:
    """将题材知识格式化为可读文本（用于 prompt 注入或工具返回）。"""
    knowledge = get_all_genre_knowledge(genres)
    lines = [f"识别题材：{'、'.join(genres)}"]
    for kind, label in [("plot_direction", "可能走向"), ("technique", "写作手法")]:
        items = knowledge.get(kind, [])
        if items:
            lines.append(f"\n{label}：")
            for item in items:
                lines.append(f"  - {item}")
    return "\n".join(lines)


# ---------- 作者语言风格提取 ----------

_IMAGERY_WORDS = ["像", "仿佛", "如同", "如", "月光", "雨", "风", "影子", "灯光", "雾气", "铁", "黄", "灰", "暗", "湿", "冷"]
_TONE_WORDS = ["冷", "暗", "沉", "静", "阴", "湿", "硬", "钝", "闷", "凉", "荒", "锈"]


def _heuristic_style(raw_text: str) -> dict[str, Any]:
    """纯规则的语言风格画像：句长、对白占比、意象密度、语气词。"""
    text = (raw_text or "").strip()
    sentences = [s.strip() for s in re.split(r"[。！？!?；;\n]", text) if s.strip()]
    total_chars = len(text) or 1
    if not sentences:
        sentences = [text]
    avg_len = sum(len(s) for s in sentences) / len(sentences)
    short_ratio = sum(1 for s in sentences if len(s) <= 12) / len(sentences)
    dialogue_chars = sum(len(m) for m in re.findall(r"[“\"]([^”\"]+)[”\"]", text))
    dialogue_ratio = dialogue_chars / total_chars
    imagery = sum(text.count(w) for w in _IMAGERY_WORDS) / total_chars * 1000
    tone = sum(text.count(w) for w in _TONE_WORDS)

    style_bits: list[str] = []
    if avg_len <= 18:
        style_bits.append("句子短促、节奏快")
    elif avg_len <= 30:
        style_bits.append("句子中等、节奏平稳")
    else:
        style_bits.append("句子偏长、有铺陈感")
    if short_ratio >= 0.4:
        style_bits.append("大量短句制造顿挫")
    if dialogue_ratio >= 0.25:
        style_bits.append("对白占比高、靠对话推动")
    elif dialogue_ratio <= 0.05:
        style_bits.append("对白极少、以叙述为主")
    if imagery >= 2.0:
        style_bits.append("意象/感官描写密集")
    if tone >= 6:
        style_bits.append("整体氛围冷峻、沉郁")
    elif tone >= 3:
        style_bits.append("略带压抑氛围")
    if not style_bits:
        style_bits.append("语言平实直白")
    summary = "、".join(style_bits) + "。"
    return {
        "summary": summary,
        "metrics": {
            "avg_sentence_len": round(avg_len, 1),
            "short_sentence_ratio": round(short_ratio, 2),
            "dialogue_ratio": round(dialogue_ratio, 2),
            "imagery_density": round(imagery, 1),
            "tone_score": int(tone),
        },
    }


def extract_author_style(raw_text: str, *, llm: LLM | None = None, language: str = "zh-CN") -> dict[str, Any]:
    """提取作者语言风格：规则画像 + 可选模型润色。

    返回结构：
      - summary:   一句话总述
      - metrics:   数值指标
      - dimensions: 分维度描述
    """
    profile = _heuristic_style(raw_text)
    m = profile["metrics"]
    dims = {
        "句式": (
            f"平均句长 {m['avg_sentence_len']} 字，短句占比 {round(m['short_sentence_ratio'] * 100)}%"
            + ("，短促有力" if m["short_sentence_ratio"] >= 0.4 else "，句式均衡")
        ),
        "节奏": (
            "句子短促、顿挫感强" if m["short_sentence_ratio"] >= 0.4
            else "节奏平缓、铺陈推进"
        ),
        "对白": (
            f"对白占比 {round(m['dialogue_ratio'] * 100)}%，靠对话推动"
            if m["dialogue_ratio"] >= 0.25
            else "对白较少，以叙述和动作描写为主"
        ),
        "意象": (
            f"意象/感官描写密集（密度 {m['imagery_density']}）"
            if m["imagery_density"] >= 2.0
            else "意象使用克制，偏白描"
        ),
        "氛围": (
            "整体氛围冷峻、沉郁" if m["tone_score"] >= 6
            else "略带压抑氛围" if m["tone_score"] >= 3
            else "氛围中性、平实"
        ),
        "语气": "克制、留白，不直说情绪" if m["dialogue_ratio"] < 0.2 and m["tone_score"] >= 3 else "直白自然",
    }
    profile["dimensions"] = dims
    if llm is not None and llm.available:
        try:
            prompt = (
                "请用 2-4 句话概括这段文本作者的写作风格（句式、节奏、对白、意象、氛围、语气），"
                "只输出风格描述本身，不要输出标题或解释。\n"
                f"规则画像参考：{json.dumps(profile, ensure_ascii=False)}\n"
                f"原文（截取）：\n{(raw_text or '')[:2000]}"
            )
            resp = llm.chat().invoke(
                [
                    {"role": "system", "content": f"你是文学编辑，请使用{language}回答。"},
                    {"role": "user", "content": prompt},
                ]
            )
            text = (resp.content or "").strip()
            if text:
                profile["summary"] = text
        except Exception:  # noqa: BLE001
            pass
    return profile


def format_author_style(raw_text: str, *, llm: LLM | None = None, language: str = "zh-CN") -> str:
    """提取并格式化作者风格为可读文本。"""
    style = extract_author_style(raw_text, llm=llm, language=language)
    lines = [f"作者语言风格：{style.get('summary', '')}"]
    for dim_name, dim_text in (style.get("dimensions") or {}).items():
        lines.append(f"  {dim_name}：{dim_text}")
    return "\n".join(lines)
