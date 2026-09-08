#!/usr/bin/env python3
"""构建 Script Workshop 桌面端发行包。

用法：
    python build.py          # 完整构建（前端 + PyInstaller）
    python build.py --skip-frontend   # 跳过前端构建，只打包 Python
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build_frontend() -> None:
    """构建 Vue 前端。"""
    print("=== 构建前端 ===")
    frontend = ROOT / "frontend"
    subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)
    dist = frontend / "dist"
    if not (dist / "index.html").exists():
        print("错误：前端构建失败，frontend/dist/index.html 不存在", file=sys.stderr)
        sys.exit(1)
    print(f"前端构建完成：{dist}")


def build_desktop() -> None:
    """运行 PyInstaller 打包。"""
    print("=== PyInstaller 打包 ===")
    spec = ROOT / "script-workshop.spec"
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(spec), "--clean", "--noconfirm"],
        cwd=ROOT,
        check=True,
    )
    out = ROOT / "dist" / "ScriptWorkshop"
    if out.exists():
        print(f"打包完成：{out}")
        print(f"  入口：{out / 'ScriptWorkshop.exe'}")
    else:
        print("警告：打包输出目录不存在，请检查 PyInstaller 日志", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 Script Workshop 桌面端")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端构建")
    args = parser.parse_args()

    if not args.skip_frontend:
        build_frontend()
    else:
        dist = ROOT / "frontend" / "dist"
        if not (dist / "index.html").exists():
            print(f"错误：跳过前端构建但 {dist} 不存在。请先运行 npm run build。", file=sys.stderr)
            sys.exit(1)
        print(f"跳过前端构建，使用已有 {dist}")

    build_desktop()
    print("\n=== 构建完成 ===")


if __name__ == "__main__":
    main()
