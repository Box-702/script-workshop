# =====================================================================
# pipeline —— 内容生产线（确定性处理，不依赖 LangGraph / HTTP）
#
# 从原文到结构化剧本的全部纯逻辑都在这一层：
#   importer    文件导入解析（txt/md/docx，编码容错）
#   chunking    文本切片（章节感知，供 prompt 组装）
#   generation  两阶段生成：故事圣经 → 场景规划
#   patch       结构化 patch 操作 + 剧本一致性校验
#   profiles    改编类型 profile（短剧 / 电影 / 剧集 / 舞台剧）
#   knowledge   题材识别与作者风格画像
#   review      改编提议的多维度评审打分
#   export      导出 txt / md / docx
#
# Agent 层（app/agent）与 API 层（app/api.py）都只是这一层的调用方。
# =====================================================================
