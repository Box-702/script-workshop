# 一次性迁移：把 media_assets 里仍指向磁盘文件的素材（file_path 非空、
# content 为空）读入数据库，然后删除磁盘文件。
# 用法：uv run python scripts/migrate_assets_to_db.py [--delete]
#   不带 --delete 只迁移不删文件（dry-run 观察输出）；确认后再加 --delete。

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.store import Store  # noqa: E402


def main() -> None:
    delete = "--delete" in sys.argv
    store = Store(get_settings().database_url)
    root = Path(get_settings().effective_workspace_root)

    with store.session() as s:
        from app.store import MediaAsset

        rows = s.query(MediaAsset).filter(MediaAsset.file_path.isnot(None)).all()
        targets = [r for r in rows if r.content is None]
        print(f"待迁移素材：{len(targets)} 条（历史磁盘记录共 {len(rows)} 条）")
        ok = fail = 0
        for a in targets:
            p = root / a.file_path
            if not p.is_file():
                print(f"  跳过（文件丢失）：{a.id} -> {p}")
                fail += 1
                continue
            a.content = p.read_bytes()
            ok += 1
            print(f"  入库：{a.id} {a.name}（{p.stat().st_size / 1024:.0f} KB）")
            if delete:
                try:
                    p.unlink()
                except OSError as e:
                    print(f"    ⚠ 文件删除失败（不影响入库）：{e}")
        s.commit()
        print(f"完成：入库 {ok} 条，跳过/丢失 {fail} 条，删除文件={delete}")


if __name__ == "__main__":
    main()
