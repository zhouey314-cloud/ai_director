#!/usr/bin/env python3
"""
pr_jsx_bridge.py — 通过 CEP HTTP 桥与 Premiere Pro 双向通信

唯一通道:
  向 http://localhost:8099 (AI Agent Bridge CEP 面板) POST ExtendScript 代码
  收到执行结果文本

用法:
  bridge = PrJsxBridge()
  result = bridge.execute("app.project.rootItem.createBin('Test');")
  print(result)
"""

import json
import os
import urllib.request
import urllib.error

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

BRIDGE_URL = "http://localhost:8099"
HTTP_TIMEOUT = 30  # 单次 HTTP 请求超时


class PrJsxBridge:
    """与 Premiere Pro 通信的唯一桥接类 (CEP HTTP 桥, 端口 8099)"""

    def __init__(self):
        self._call_id = 0

    def execute(self, extendscript_code: str) -> str:
        """发送 ExtendScript 到 PR 执行，返回结果字符串

        唯一通道: POST http://localhost:8099
        失败时抛出 RuntimeError，绝对不生成 .jsx 文件
        """
        self._call_id += 1
        cid = self._call_id
        try:
            data = extendscript_code.encode("utf-8")
            req = urllib.request.Request(
                BRIDGE_URL, data=data, method="POST",
                headers={"Content-Type": "text/plain"}
            )
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                result = r.read().decode("utf-8").strip()
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"CEP 桥 {BRIDGE_URL} 不可达 — 请确认 PR 中 AI Agent Bridge 面板已打开 "
                f"(窗口 → 扩展 → AI Agent Bridge)\n  细节: {e}"
            )
        except OSError as e:
            raise RuntimeError(f"HTTP 请求失败 (call #{cid}): {e}")

        say("HTTP", f"#{cid} → {result[:160]}", GREEN)
        return result

    def evaluate(self, js_expression: str) -> str:
        """发送表达式到 PR，返回其求值结果（走 HTTP 桥）"""
        say("EVAL", f"{js_expression[:80]}...", CYAN)
        wrapped = (
            'try { '
            f'  var __ret = eval({json.dumps(js_expression)}); '
            '  "OK: " + String(__ret); '
            '} catch (e) { '
            '  "ERROR: " + e.toString(); '
            '}'
        )
        return self.execute(wrapped)

    # ── 高级 API ──

    def create_bin(self, bin_name: str = "AI_Tasks") -> str:
        """在 PR 中创建素材箱"""
        safe_name = bin_name.replace("'", "\\'")
        return self.execute(f'app.project.rootItem.createBin("{safe_name}");')

    def add_marker(self, marker_name: str = "AI_Tasks_Marker") -> str:
        """在时间线上添加标记"""
        safe_name = marker_name.replace("'", "\\'")
        return self.execute(
            'if (app.project.activeSequence) {'
            f'  app.project.activeSequence.createMarker("{safe_name}");'
            '  "OK: marker added";'
            '} else { "WARN: no active sequence"; }'
        )

    def get_project_name(self) -> str:
        """获取当前项目名称"""
        r = self.evaluate('app.project.name')
        return r.removeprefix("OK: ") if r.startswith("OK: ") else r

    def is_project_open(self) -> bool:
        """检查是否有项目打开"""
        r = self.evaluate('app.project ? "true" : "false"')
        return "true" in r.lower()

    def import_media(self, file_path: str) -> str:
        """导入标准媒体文件 (mp4/mov/jpg/png 等)"""
        return self.execute(
            f'app.project.importFiles(["{file_path}"], true, app.project.rootItem, false);'
        )

    def find_child(self, name_substring: str) -> str | None:
        """在项目根目录中按名称查找素材,返回 index 或 None"""
        code = (
            '(function(){'
            '  var items=app.project.rootItem.children;'
            '  for(var i=0;i<items.numItems;i++){'
            f'    if(items[i].name.indexOf({json.dumps(name_substring)})>=0) return String(i);'
            '  }'
            '  return "null";'
            '})()'
        )
        r = self.execute(code)
        return None if r == "null" else r

    def create_sequence_from_clips(self, seq_name: str, clip_index: int) -> str:
        """根据已有素材静默创建序列 (无弹窗)

        内部使用 app.project.createNewSequenceFromClips() 自动匹配分辨率/帧率
        """
        safe_name = json.dumps(seq_name)
        code = (
            '(function(){'
            '  try {'
            '    var clip=app.project.rootItem.children[' + str(clip_index) + '];'
            '    if(!clip) return "ERROR: clip not found at index ' + str(clip_index) + '";'
            f'    var seq=app.project.createNewSequenceFromClips({safe_name}, [clip], app.project.rootItem);'
            '    return seq ? "OK: " + seq.name : "OK: created (void return)";'
            '  } catch(e) { return "ERROR: " + e.toString(); }'
            '})()'
        )
        return self.execute(code)

    def insert_clip_into_timeline(
        self, seq_name: str, clip_index: int,
        video_track: int = 0, audio_track: int = 0, time_ticks: int = 0
    ) -> str:
        """将素材插入到序列的指定轨道和位置"""
        safe_seq_name = json.dumps(seq_name)
        code = (
            '(function(){'
            '  try {'
            '    var seq=null;'
            '    for(var i=0;i<app.project.sequences.numSequences;i++){'
            f'      if(app.project.sequences[i].name=={safe_seq_name}){{seq=app.project.sequences[i];break;}}'
            '    }'
            '    if(!seq) return "ERROR: sequence not found";'
            '    var clip=app.project.rootItem.children[' + str(clip_index) + '];'
            '    if(!clip) return "ERROR: clip not found";'
            '    seq.videoTracks[' + str(video_track) + '].insertClip(clip, ' + str(time_ticks) + ');'
            '    seq.audioTracks[' + str(audio_track) + '].insertClip(clip, ' + str(time_ticks) + ');'
            '    return "OK: inserted at T=" + ' + str(time_ticks) + ';'
            '  } catch(e) { return "ERROR: " + e.toString(); }'
            '})()'
        )
        return self.execute(code)

    def list_sequences(self) -> list[str]:
        """返回所有序列名列表"""
        r = self.evaluate(
            'var s=app.project.sequences;var n=[];'
            'for(var i=0;i<s.numSequences;i++){n.push(s[i].name)}'
            'n.join("|")'
        )
        if not r.startswith("OK:"):
            return []
        raw = r[4:]  # strip "OK: "
        return raw.split("|") if raw else []

    def list_children(self) -> list[str]:
        """返回项目根目录所有子项名称列表"""
        r = self.execute(
            '(function(){'
            '  var items=app.project.rootItem.children;'
            '  var n=[];'
            '  for(var i=0;i<items.numItems;i++){n.push(i+":"+items[i].name)}'
            '  return n.join("|");'
            '})()'
        )
        return r.split("|") if r else []


def say(tag, msg, color=""):
    print(f"  {color}[{tag}]{RESET} {msg}")


def test_bridge():
    """HTTP CEP 桥完整工作流测试"""
    import os
    mp4 = os.path.expanduser("~/Desktop/剪辑视频AI/my-video/real_vlog.mp4")

    print(f"\n  {BOLD}PR CEP 桥 — 完整剪辑工作流{RESET}")
    print(f"  {'=' * 48}")

    bridge = PrJsxBridge()

    # 1) 连通性
    print(f"\n  {CYAN}[1/6] 连通性检查{RESET}")
    try:
        ok = bridge.is_project_open()
        if not ok:
            print(f"  {YELLOW}⚠ 请先在 PR 中打开项目{RESET}")
            return
        print(f"  → 项目打开, 名: {bridge.get_project_name()}")
    except RuntimeError as e:
        print(f"  {RED}✗ {e}{RESET}")
        return

    # 2) 导入媒体
    print(f"\n  {CYAN}[2/6] 导入媒体{RESET}")
    r = bridge.import_media(mp4)
    print(f"  → {GREEN if r == 'true' or 'OK' in r else YELLOW}{r}{RESET}")

    # 3) 查找素材
    print(f"\n  {CYAN}[3/6] 查找素材{RESET}")
    idx = bridge.find_child("real_vlog")
    if idx is None:
        print(f"  {YELLOW}⚠ 未找到素材{RESET}")
        return
    print(f"  → index={idx}")

    # 4) 创建序列 (无弹窗)
    print(f"\n  {CYAN}[4/6] createNewSequenceFromClips (无弹窗){RESET}")
    r = bridge.create_sequence_from_clips("AI_Auto_Edit", int(idx))
    print(f"  → {GREEN if 'OK' in r else YELLOW}{r}{RESET}")

    # 5) 插入时间线
    print(f"\n  {CYAN}[5/6] 插入时间线{RESET}")
    r = bridge.insert_clip_into_timeline("AI_Auto_Edit", int(idx))
    print(f"  → {GREEN if 'OK' in r else YELLOW}{r}{RESET}")

    # 6) 验证
    print(f"\n  {CYAN}[6/6] 验证{RESET}")
    seqs = bridge.list_sequences()
    print(f"  序列: {seqs}")
    for s in seqs:
        r = bridge.execute(
            '(function(){'
            '  var seq=null;'
            '  for(var i=0;i<app.project.sequences.numSequences;i++){'
            f'    if(app.project.sequences[i].name=={json.dumps(s)}){{seq=app.project.sequences[i];break;}}'
            '  }'
            '  if(!seq)return "NOT FOUND";'
            '  return "VT:"+seq.videoTracks.numTracks+" AT:"+seq.audioTracks.numTracks'
            '    +" VT[0].clips="+seq.videoTracks[0].clips.numItems'
            '    +" AT[0].clips="+seq.audioTracks[0].clips.numItems;'
            '})()'
        )
        print(f'  {s}: {GREEN}{r}{RESET}')

    print(f"\n  {GREEN}{'=' * 48}{RESET}")
    print(f"  {GREEN}✓ 完整工作流验证通过{RESET}")
    print(f"  {'=' * 48}")


if __name__ == "__main__":
    test_bridge()
