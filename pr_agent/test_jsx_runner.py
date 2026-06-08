#!/usr/bin/env python3
"""
test_jsx_runner.py — 通过 CEP HTTP 桥向 Premiere Pro 发送 ExtendScript

唯一通道: POST http://localhost:8099

前置条件:
  1. PR 中: 窗口 → 扩展 → AI Agent Bridge (面板显示"AI 接收器运行中")
  2. Python urllib 直接 POST 到 localhost:8099
"""

import urllib.request
import urllib.error
from pathlib import Path

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

BRIDGE_URL = "http://localhost:8099"


def send_extendscript(code: str, timeout: int = 30) -> str:
    """通过 HTTP POST 发送 ExtendScript 到 CEP 扩展, 返回结果"""
    data = code.encode("utf-8")
    req = urllib.request.Request(
        BRIDGE_URL, data=data, method="POST",
        headers={"Content-Type": "text/plain"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8").strip()


def main():
    print(f"\n  {BOLD}Python → Premiere Pro CEP 桥通信测试{RESET}")
    print(f"  {'=' * 48}")
    print(f"  唯一通道: HTTP POST {BRIDGE_URL}")
    print(f"  (无降级, 无 .jsx 文件生成)")
    print()

    try:
        # 测试 1
        print(f"  {CYAN}[测试 1] 检查项目状态 + 创建素材箱{RESET}")
        code = (
            '(function() {'
            '  var result = "";'
            '  try {'
            '    var project = app.project;'
            '    if (!project) { result = "ERROR: No project open"; }'
            '    else {'
            '      var bin = project.rootItem.createBin("AI Tasks");'
            '      result = bin ? "OK: bin created" : "WARN: bin returned null";'
            '      var seq = project.activeSequence;'
            '      if (seq) { seq.createMarker("AI Marker"); result += ", marker added"; }'
            '      else { result += ", no active sequence"; }'
            '    }'
            '  } catch (e) { result = "ERROR: " + e.toString(); }'
            '  return result;'
            '})();'
        )
        result = send_extendscript(code)
        if result.startswith("OK"):
            print(f"  {GREEN}✓ {result}{RESET}")
        elif result.startswith("ERROR"):
            print(f"  {YELLOW}⚠ {result}{RESET}")
        else:
            print(f"  → {result}")

        # 测试 2
        print(f"\n  {CYAN}[测试 2] 获取项目名{RESET}")
        result = send_extendscript("app.project ? app.project.name : 'No project';")
        print(f"  → {GREEN if result else YELLOW}{result or '(空)'}{RESET}")

        # 测试 3
        print(f"\n  {CYAN}[测试 3] 添加时间线标记{RESET}")
        result = send_extendscript(
            'if (app.project && app.project.activeSequence) {'
            'app.project.activeSequence.createMarker("AI_Marker");'
            '"OK: marker added";'
            '} else { "WARN: no active sequence"; }'
        )
        print(f"  → {GREEN if 'OK' in result else YELLOW}{result}{RESET}")

        print(f"\n  {GREEN}{'=' * 48}{RESET}")
        print(f"  {GREEN}✓ 测试完成{RESET}")
        print(f"  {'=' * 48}")
        print()

    except (urllib.error.URLError, OSError) as e:
        print(f"\n  {RED}✗ 通信失败{RESET}")
        print(f"  {YELLOW}  CEP 桥 {BRIDGE_URL} 不可达{RESET}")
        print(f"  {YELLOW}  请确保: 1) PR 已打开 2) 启动了 AI Agent Bridge 面板{RESET}")
        print(f"  {YELLOW}  PR 菜单: 窗口 → 扩展 → AI Agent Bridge{RESET}")
        print(f"  {YELLOW}  错误: {e}{RESET}")
        raise


if __name__ == "__main__":
    main()
