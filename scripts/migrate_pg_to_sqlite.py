# =====================================================================
# migrate_pg_to_sqlite.py —— 把存量 Postgres 数据一次性搬进 SQLite
#
# 背景：开发阶段从 Docker Postgres 切换到 SQLite（见 docs/DECISIONS.md）。
# 本脚本把旧 Postgres 库里所有表按依赖顺序整表复制到新 SQLite 文件库，
# 两边表结构一致（都由 app/store.py 的 ORM 建出）。
#
# 用法：
#   python scripts/migrate_pg_to_sqlite.py \
#       --source postgresql+psycopg://script:script@localhost:5432/script_agent \
#       --target  sqlite:///data/script_agent.db
#
# 幂等性：目标表已有数据时跳过该表（不覆盖，可安全重复执行）。
# =====================================================================

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本在仓库根下直接 `python scripts/xxx.py` 也能 import app 包。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect  # noqa: E402

from app.store import Base, _ensure_sqlite_dir  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Postgres → SQLite 存量数据迁移")
    parser.add_argument(
        "--source", required=True,
        help="旧 Postgres 连接串，如 postgresql+psycopg://script:script@localhost:5432/script_agent",
    )
    parser.add_argument(
        "--target", required=True,
        help="新 SQLite 连接串，如 sqlite:///data/script_agent.db",
    )
    args = parser.parse_args()

    src_engine = create_engine(args.source, connect_args={"connect_timeout": 5})
    if not inspect(src_engine).has_table("projects"):
        print("源库里没有 projects 表：没有可迁移的数据，直接结束。")
        return 0

    _ensure_sqlite_dir(args.target)
    dst_engine = create_engine(args.target, connect_args={"check_same_thread": False})
    Base.metadata.create_all(dst_engine)

    # 按依赖顺序复制（sorted_tables 保证被引用的表先建/先插）。
    # 源库里还不存在的表（如刚加的 chat_images）直接跳过——新功能表没有存量数据；
    # 源表缺新列（如 chat_messages.images_json）时按源列复制，缺的列由 SQLite 端默认值兜底。
    src_inspect = inspect(src_engine)
    src_tables = set(src_inspect.get_table_names())
    src_meta = Base.metadata  # 表结构以 ORM 为准；两边一致
    ok_tables, skipped = [], []
    with src_engine.connect() as src_conn, dst_engine.begin() as dst_conn:
        for table in src_meta.sorted_tables:
            name = table.name
            if name not in src_tables:
                skipped.append(f"{name}（源库无此表，跳过）")
                continue
            src_cols = {c["name"] for c in src_inspect.get_columns(name)}
            missing = [c.name for c in table.columns if c.name not in src_cols]
            select_table = table
            if missing:
                from sqlalchemy import select as sa_select

                select_table = sa_select(*[c for c in table.columns if c.name in src_cols])
            dst_count = dst_conn.execute(
                __import__("sqlalchemy").text(f"SELECT COUNT(*) FROM {name}")
            ).scalar_one()
            if dst_count > 0:
                skipped.append(f"{name}（目标已有 {dst_count} 行，跳过）")
                continue
            rows = [dict(r._mapping) for r in src_conn.execute(select_table.select())]
            if rows:
                if missing:
                    # 缺失列用 ORM 列声明的 default 补（images_json → '[]' 等），不能填 None。
                    col_defaults = {}
                    for col in table.columns:
                        if col.name in missing:
                            default = col.default.arg if col.default is not None and col.default.is_scalar else None
                            col_defaults[col.name] = default
                    dst_conn.execute(
                        table.insert(),
                        [{**row, **col_defaults} for row in rows],
                    )
                else:
                    dst_conn.execute(table.insert(), rows)
            note = f"（{len(rows)} 行）" + (f"，缺列 {','.join(missing)} 已按默认值补齐" if missing else "")
            ok_tables.append(f"{name}{note}")

    print("迁移完成：")
    for line in ok_tables:
        print("  ✓", line)
    for line in skipped:
        print("  -", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
