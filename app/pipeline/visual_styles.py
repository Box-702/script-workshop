# =====================================================================
# visual_styles.py —— 画风（与改编类型正交的一个维度）
#
# 为什么单独成模块，而不是再加一个 adaptation_type：
#   短剧是按**载体与分发**定义的（竖屏、1–2 分钟、前 3 秒抓人、按完播投流），
#   漫剧是按**画风**定义的（二次元、分格、符号化表演）。两者不在同一根轴上——
#   漫剧就是「短剧 + 二次元画风」，是短剧的子类，不是并列体裁。
#   做成并列类型，会让导演拆镜、节奏取值、连续性校验全部为一个画风分叉；
#   而画风真正只影响三处：
#     1. 美术锚与定妆图 / 场景图的生成 prompt（立绘还是剧照）；
#     2. 视频提示词里的画风声明（写实摄影还是赛璐璐动画）；
#     3. 配音气质（写实成熟 vs 年轻二次元）。
#   所以：**类型决定怎么拍，画风决定怎么画**。两者相乘，不做组合爆炸。
#
# 用法：项目 video_style 里的 ``visual_style`` 字段（"realistic"/"anime"/…），
# 由美术指导写入、DP 与定妆图、选角读取。
# =====================================================================

from __future__ import annotations

from typing import Any

from ..domain import normalize_visual_style

# 每个画风给出四段可直接拼进 prompt 的文本。
# 注意：写 prompt 时要说「是二维动画」而不只是「动漫风格」——视频模型会把
# 后者理解成「有点动画感的实拍」，出来是不伦不类的东西。
VISUAL_STYLES: dict[str, dict[str, Any]] = {
    "realistic": {
        "label": "写实实拍",
        "description": "真人实拍，电影摄影质感",
        "render_note": "写实电影摄影，真实人物与实景，自然光影，35mm 镜头质感",
        "character_sheet": (
            "角色定妆照。{desc}。正面半身像，纯灰色背景，光线均匀柔和，写实电影质感，"
            "五官清晰、服装细节清楚；人物必须是中国人（东亚面孔）。画面里不要出现任何文字。"
        ),
        "environment_sheet": (
            "场景定妆图。{desc}。广角固定机位空镜，画面里没有任何人物；写实电影质感，"
            "光线氛围与描述一致，空间关系清楚。画面里不要出现任何文字。"
        ),
        "negative": "动漫风格、卡通、插画、3D 渲染、塑料感",
        "voice_pool": "realistic",
    },
    "anime": {
        "label": "二次元（漫剧）",
        "description": "日式二维动画，赛璐璐上色",
        "render_note": (
            "日式二维动画（2D cel-shaded anime），干净描边、平涂上色、"
            "赛璐璐阴影，画面是画出来的而不是拍出来的"
        ),
        "character_sheet": (
            "角色立绘（character sheet）。{desc}。正面半身，纯灰色背景，"
            "日式二维动画赛璐璐上色，清晰描边，发型与瞳色固定、五官比例一致；"
            "人物为东亚面孔的二次元角色。画面里不要出现任何文字。"
        ),
        "environment_sheet": (
            "场景设定图。{desc}。广角空镜，日式二维动画背景美术（背景画风格），"
            "赛璐璐上色，画面里没有任何人物。不要出现任何文字。"
        ),
        "negative": "真人、写实照片、3D 渲染、欧美卡通",
        "voice_pool": "anime",
    },
    "3d": {
        "label": "三维动画",
        "description": "3D 动画电影质感",
        "render_note": "三维动画渲染（3D animation），电影级材质与体积光，皮克斯式角色设计",
        "character_sheet": (
            "3D 角色设定图。{desc}。正面半身，纯灰色背景，三维动画渲染，"
            "材质与发型结构清楚；东亚面孔。画面里不要出现任何文字。"
        ),
        "environment_sheet": (
            "3D 场景设定图。{desc}。广角空镜，画面里没有人物，三维动画渲染，"
            "空间结构与光照清楚。不要出现任何文字。"
        ),
        "negative": "真人照片、二维线稿、像素风",
        "voice_pool": "anime",  # 三维动画片同样偏年轻化配音
    },
    "ink": {
        "label": "水墨国风",
        "description": "水墨／国风绘画质感",
        "render_note": "中国水墨画风格，留白构图，墨色浓淡与皴法笔触，宣纸质感",
        "character_sheet": (
            "水墨人物设定图。{desc}。正面半身，宣纸底，水墨笔触勾勒，"
            "墨色浓淡分明，留白构图；东亚面孔。画面里不要出现任何文字。"
        ),
        "environment_sheet": (
            "水墨场景设定图。{desc}。广角空镜，无人物，水墨山水／建筑笔触，"
            "大量留白，宣纸质感。不要出现任何文字。"
        ),
        "negative": "照片、3D 渲染、欧美插画、浓艳色彩",
        "voice_pool": "realistic",
    },
}

DEFAULT_VISUAL_STYLE = "realistic"

# 前端下拉用的清单。
STYLE_CHOICES: list[dict[str, str]] = [
    {"value": key, "label": spec["label"], "description": spec["description"]}
    for key, spec in VISUAL_STYLES.items()
]


def get_visual_style(name: object = None) -> dict[str, Any]:
    """取画风配置；未知值回退实拍。返回的 dict 保证含全部键。"""
    key = normalize_visual_style(name)
    return VISUAL_STYLES.get(key, VISUAL_STYLES[DEFAULT_VISUAL_STYLE])


def visual_style_key(name: object = None) -> str:
    """规整后的画风键（用于持久化）。"""
    return normalize_visual_style(name)


def character_prompt(name: str, appearance: str, style: object = None) -> str:
    """角色定妆/立绘 prompt：画风决定「剧照」还是「立绘」。"""
    spec = get_visual_style(style)
    desc = (appearance or "").strip() or name
    return spec["character_sheet"].format(desc=desc)


def environment_prompt(name: str, description: str, style: object = None) -> str:
    """场景图 prompt：写实是「空镜定妆图」，二次元是「背景美术」。"""
    spec = get_visual_style(style)
    desc = (description or "").strip() or name
    return spec["environment_sheet"].format(desc=desc)
