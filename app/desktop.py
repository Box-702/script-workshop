# =====================================================================
# desktop.py —— 桌面端启动器
#
# 使用 PyWebView 打开原生窗口（保留系统标题栏）。
# Windows 11 下自动设置暗色标题栏，与深色主题一致。
# =====================================================================

from __future__ import annotations

import logging
import platform
import socket
import sys
import threading
import time

log = logging.getLogger("desktop")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 20.0) -> bool:
    import urllib.request

    url = f"http://127.0.0.1:{port}/api/healthz"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _run_server(port: int) -> None:
    import uvicorn

    from .main import create_app

    app = create_app()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port,
        log_level="warning", access_log=False,
    )
    uvicorn.Server(config).run()


def _set_dark_titlebar(hwnd: int) -> None:
    """Windows 11+: 设置窗口标题栏为暗色模式。"""
    try:
        import ctypes
        import ctypes.wintypes

        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        # DWMWA_CAPTION_COLOR = 35
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_CAPTION_COLOR = 35

        dwmapi = ctypes.windll.dwmapi

        # 启用暗色模式
        dark = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(dark),
            ctypes.sizeof(dark),
        )

        # 标题栏颜色设为与 --panel 一致的暖黑
        # OKLCH(0.21 0.009 80) ≈ RGB(48, 45, 42) = 0x2A2D30 (BGR)
        color = ctypes.wintypes.DWORD(0x00302D2A)  # BGR 格式
        dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd),
            DWMWA_CAPTION_COLOR,
            ctypes.byref(color),
            ctypes.sizeof(color),
        )
        print("已设置暗色标题栏", flush=True)
    except Exception as e:
        print(f"暗色标题栏跳过：{e}", flush=True)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    sys._desktop_mode = True

    port = _find_free_port()
    print(f"启动服务于 127.0.0.1:{port} ...", flush=True)

    server_thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    server_thread.start()

    if not _wait_for_server(port):
        print("错误：服务启动超时。", file=sys.stderr, flush=True)
        sys.exit(1)

    url = f"http://127.0.0.1:{port}"
    print(f"服务就绪：{url}", flush=True)

    try:
        import webview
    except ImportError:
        import webbrowser

        log.warning("未安装 pywebview，降级为浏览器。pip install pywebview")
        webbrowser.open(url)
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass
        return

    window = webview.create_window(
        title="剧本工坊 · Script Workshop",
        url=url,
        width=1360,
        height=900,
        min_size=(960, 640),
        text_select=True,
    )

    # Windows 11+: 延迟设置暗色标题栏（等窗口创建完成）
    if platform.system() == "Windows":
        def _on_loaded():
            time.sleep(2)
            try:
                # pywebview 窗口 native 对象的 Handle 即为 HWND
                hwnd = window.native.Handle.ToInt32()
                print(f"HWND: {hwnd}", flush=True)
                _set_dark_titlebar(hwnd)
            except Exception as e:
                print(f"暗色标题栏跳过：{e}", flush=True)
        threading.Thread(target=_on_loaded, daemon=True).start()

    print("打开窗口...", flush=True)
    webview.start(debug=False)
    print("窗口已关闭", flush=True)


if __name__ == "__main__":
    main()
