"""
Premiere Pro 自动化桥接模块 - AppleScript GUI Scripting 实现

原理：
  利用 macOS System Events 模拟键盘操作（Cmd+I 导入 → Cmd+Shift+G 跳转到路径），
  实现无鼠标自动导入 FCPXML 序列到当前项目。

前提：
  1. Adobe Premiere Pro 2024 已安装
  2. 系统已授予 Terminal/iTerm2 辅助功能权限
     (系统设置 → 隐私与安全性 → 辅助功能)
"""

import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "Adobe Premiere Pro 2024"

# ---------------------------------------------------------------------------
# AppleScript 执行器
# ---------------------------------------------------------------------------


def _run_as(source: str) -> subprocess.CompletedProcess:
    """执行一段 AppleScript 代码"""
    return subprocess.run(
        ["osascript", "-e", source],
        capture_output=True, text=True,
        timeout=90,
    )


# ---------------------------------------------------------------------------
# 状态检测
# ---------------------------------------------------------------------------


def is_installed() -> bool:
    """检查 Premiere Pro 是否已安装到系统"""
    try:
        r = _run_as(f'tell application "{APP_NAME}" to get name')
        return r.returncode == 0
    except FileNotFoundError:
        # osascript 不存在（非 macOS）
        return False


def is_running() -> bool:
    """检查 Premiere Pro 是否正在运行"""
    try:
        r = _run_as(
            f'tell application "System Events" to '
            f'exists (process "{APP_NAME}")'
        )
        return r.stdout.strip() == "true"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 核心：唤醒 + 导入
# ---------------------------------------------------------------------------

def activate_and_import(fcpxml_path: str) -> bool:
    """唤醒 Premiere Pro 并自动导入 FCPXML 序列。

    流程：
      1. 如果 PR 未运行则启动，等待就绪
      2. 把 PR 带到前台
      3. Cmd+I → 打开导入对话框
      4. Cmd+Shift+G → 前往文件夹
      5. 键入 FCPXML 绝对路径
      6. Enter → 定位文件
      7. Enter → 执行导入

    Args:
        fcpxml_path:   .fcpxml 文件的绝对路径

    Returns:
        True 如果操作完成（不保证 PR 内部处理成功，但操作已发出）
        False 如果安装检测或系统支持失败
    """
    if not is_installed():
        print("  ⚠ 未检测到 Adobe Premiere Pro 2024，跳过自动导入")
        return False

    abs_path = os.path.abspath(fcpxml_path)
    if not os.path.isfile(abs_path):
        print(f"  ⚠ FCPXML 文件不存在: {abs_path}")
        return False

    # AppleScript 字符串中的反斜杠和引号需要转义
    safe_path = abs_path.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
-- 辅助函数：检测 PR 是否在前台
on isFrontmost(procName)
    tell application "System Events"
        set frontProc to name of first process whose frontmost is true
        return frontProc is procName
    end tell
end isFrontmost

-- 1. 启动/激活 Premiere Pro
set wasRunning to false
tell application "System Events"
    set wasRunning to exists (process "{APP_NAME}")
end tell

tell application "{APP_NAME}"
    activate
end tell

if not wasRunning then
    -- 首次启动较慢，等待至前台可见
    repeat 30 times
        delay 1
        if isFrontmost("{APP_NAME}") then exit repeat
    end repeat
else
    delay 2
end if

-- 2. 通过 System Events GUI 操作导入
tell application "System Events"
    tell process "{APP_NAME}"

        -- 确保窗口已就绪
        if not wasRunning then
            delay 3
        end if

        -- 第 1 步：Cmd+I (导入快捷键)
        keystroke "i" using command down
        delay 1

        -- 第 2 步：Cmd+Shift+G (前往文件夹)
        keystroke "g" using {{command down, shift down}}
        delay 0.5

        -- 第 3 步：粘贴文件路径
        keystroke "{safe_path}"
        delay 0.5

        -- 第 4 步：回车 - 前往文件
        keystroke return
        delay 1.5

        -- 第 5 步：回车 - 执行导入
        keystroke return
    end tell
end tell
'''

    try:
        r = _run_as(script)
    except subprocess.TimeoutExpired:
        print("  ⚠ AppleScript 执行超时（PR 启动可能较慢或操作卡住）")
        return False

    if r.returncode == 0:
        print(f"  ✅ Premiere Pro 已接收导入指令")
        print(f"  📁 序列文件: {abs_path}")
        return True
    else:
        err = r.stderr.strip()
        print(f"  ⚠ AppleScript 执行异常: {err}")
        print("  常见原因：")
        print("    - 系统设置 → 隐私与安全性 → 辅助功能 未授权终端")
        print("    - Premiere Pro 未打开任何项目")
        print("  提示：手动打开 PR 并创建一个项目后再试")
        return False
