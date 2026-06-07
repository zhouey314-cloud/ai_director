"""
Premiere Pro 自动化桥接模块 - macOS open 命令

用法：
  直接调用 activate_and_import("/绝对路径/到/xxx_premiere.fcpxml")

原理：
  通过 macOS 原生 `open -a "Adobe Premiere Pro 2024" <文件>` 命令，
  让 Premiere Pro 打开 FCPXML 文件（PR 会自动识别为序列导入）。

  比 AppleScript + 模拟按键稳定得多，无需辅助功能权限。

前提：
  建议在运行前在 PR 中打开好一个项目（即使是空白项目）。
"""

import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "Adobe Premiere Pro 2024"


def is_installed() -> bool:
    """检查 Premiere Pro 是否已安装"""
    try:
        r = subprocess.run(
            ["mdfind", "kMDItemKind == 'Application'", "-name", "Premiere Pro"],
            capture_output=True, text=True, timeout=10,
        )
        return APP_NAME in r.stdout
    except Exception:
        return False


def is_running() -> bool:
    """检查 Premiere Pro 进程是否存在"""
    try:
        r = subprocess.run(
            ["pgrep", "-q", "-x", APP_NAME],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def activate_and_import(fcpxml_path: str) -> bool:
    """通过 `open -a` 让 Premiere Pro 导入 FCPXML 序列。

    这个命令等效于在 Finder 中双击 .fcpxml 文件，
    PR 会自动将其识别为 Final Cut Pro XML 导入并创建序列。

    Args:
        fcpxml_path: .fcpxml 文件的绝对路径

    Returns:
        True 如果 open 命令发送成功
    """
    abs_path = os.path.abspath(fcpxml_path)

    # ── 前置检查 ──
    if not os.path.isfile(abs_path):
        print(f"  ⚠ FCPXML 文件不存在: {abs_path}")
        return False

    if not is_installed():
        print("  ⚠ 未检测到 Adobe Premiere Pro 2024，跳过自动导入")
        print("  如需手动导入：File → Import → 选择 .fcpxml 文件")
        return False

    already_running = is_running()

    # ── 执行 open -a ──
    print(f"\n  正在通过 open -a 唤醒 Premiere Pro ...")
    try:
        r = subprocess.run(
            ["open", "-a", APP_NAME, abs_path],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("  ⚠ 命令执行超时")
        return False

    if r.returncode != 0:
        print(f"  ⚠ open 命令失败: {r.stderr.strip()}")
        return False

    # ── 日志提示 ──
    if already_running:
        print("  ✅ 已将 FCPXML 发送至 Premiere Pro，序列应已导入当前项目")
    else:
        print("  ✅ FCPXML 已发送，Premiere Pro 正在启动（首次启动较慢）")

    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║  ⚠ 重要提示                                            ║")
    print("  ║                                                         ║")
    print("  ║  请确保 PR 中已打开一个项目，否则导入会静默失败！         ║")
    print("  ║                                                         ║")
    print("  ║  如果没有：File → New → Project → 随便起个名即可         ║")
    print("  ║                                                         ║")
    print("  ║  导入后项目面板会出现一个名为 AI_Edit_xxx 的序列，        ║")
    print("  ║  双击它即可在时间线上查看 AI 剪好的成片。                ║")
    print("  ╚══════════════════════════════════════════════════════════╝")

    return True
