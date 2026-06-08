#!/usr/bin/env python3
"""
ai_director.py — AI 导演剪辑控制器

无 insertClip 方案: createNewSequenceFromClips 一次性放入所有 clip,
然后逐个设置 start/end/inPoint/outPoint, 零多余 clip 残留.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pr_jsx_bridge import PrJsxBridge, say, GREEN, YELLOW, CYAN, RESET, RED, BOLD

DEMO_EDITS = [
    {"file": "my-video/real_vlog.mp4", "in_point": 3.0,  "out_point": 7.0,   "label": "开场"},
    {"file": "my-video/real_vlog.mp4", "in_point": 15.0, "out_point": 20.0,  "label": "高光1"},
    {"file": "my-video/real_vlog.mp4", "in_point": 30.0, "out_point": 35.0,  "label": "高光2"},
]

SEQ_NAME = f"AI_DirectCut_{int(time.time())}"
GRAN = 254016000000


def _ticks(sec):
    return str(int(round(sec * GRAN)))


def _exec(bridge, code: str) -> str:
    """执行 ExtendScript, 返回结果"""
    return bridge.execute(
        '(function(){ try { ' + code + ' } catch(e){return "ERROR:"+e.toString().substring(0,200);} })()'
    )


def run(edits: list[dict]):
    bridge = PrJsxBridge()
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print(f"\n  {BOLD}AI 导演 — 最终工作流{RESET}")
    print(f"  {'=' * 48}")
    print(f"  指令: {len(edits)}  序列: {SEQ_NAME}")
    print()

    # ── 1) 项目 ──
    print(f"  {CYAN}[1/5] 项目{RESET}")
    if not bridge.is_project_open():
        print(f"  {YELLOW}⚠ 需要打开项目{RESET}")
        return False
    print(f"  → {bridge.get_project_name()}")

    # ── 2) 素材 ──
    print(f"\n  {CYAN}[2/5] 素材{RESET}")
    first_file = edits[0]["file"]
    basename = os.path.basename(first_file)
    idx = bridge.find_child(basename)
    if idx is not None:
        src_idx = int(idx)
    else:
        ap = os.path.join(base_dir, first_file)
        bridge.import_media(ap)
        src_idx = int(bridge.find_child(basename) or -1)
    if src_idx < 0:
        print(f"  {RED}✗ 素材未找到{RESET}")
        return False
    print(f"  → {basename} @ {src_idx}")

    # ── 3) 创建序列 — 用所有 clip 引用一次性创建 ──
    print(f"\n  {CYAN}[3/5] 创建序列{RESET}")
    n = len(edits)
    r = bridge.execute(
        '(function(){'
        '  try {'
        f'    var clip=app.project.rootItem.children[{src_idx}];'
        '    var clips=[];'
        f'    for(var _i=0;_i<{n};_i++) clips.push(clip);'
        f'    app.project.createNewSequenceFromClips({json.dumps(SEQ_NAME)},clips,app.project.rootItem);'
        '    for(var i=0;i<app.project.sequences.numSequences;i++){'
        f'      if(app.project.sequences[i].name=={json.dumps(SEQ_NAME)}) return "OK:"+i;'
        '    }'
        '    return "ERROR: seq not found after create";'
        '  } catch(e){return "ERROR:"+e.toString().substring(0,100);}'
        '})()'
    )
    if not r.startswith("OK:"):
        print(f"  {RED}✗ 创建失败: {r[:120]}{RESET}")
        print(f"  {YELLOW}⚠ 回退: 使用 1-clip + insertClip 方案...{RESET}")

        # 回退: 1-clip 创建 + insertClip 方案
        r2 = bridge.execute(
            '(function(){'
            '  try {'
            f'    var clip=app.project.rootItem.children[{src_idx}];'
            f'    app.project.createNewSequenceFromClips({json.dumps(SEQ_NAME)},[clip],app.project.rootItem);'
            '    for(var i=0;i<app.project.sequences.numSequences;i++){'
            f'      if(app.project.sequences[i].name=={json.dumps(SEQ_NAME)})return "OK:"+i;'
            '    }return "ERROR: seq not found";'
            '  }catch(e){return "ERROR:"+e.toString().substring(0,80);}'
            '})()'
        )
        if not r2.startswith("OK:"):
            print(f"  {RED}✗ 回退也失败: {r2[:80]}{RESET}")
            return False
        seq_idx = int(r2[3:])
        print(f"  → {SEQ_NAME} @ sequences[{seq_idx}] (1-clip 模式)")

        # ── 4b) insertClip 模式 ──
        print(f"\n  {CYAN}[4/5] 剪辑 (insertClip 模式){RESET}")
        pos_ticks = 0
        for i, e in enumerate(edits):
            label = e.get("label", f"seg{i}")
            in_t = _ticks(e["in_point"])
            out_t = _ticks(e["out_point"])
            dur_t = int(out_t) - int(in_t)
            end_t = pos_ticks + dur_t
            say("CUT", f"[{i+1}/{n}] {label}  {e['in_point']}s→{e['out_point']}s T={round(pos_ticks/GRAN,1)}s")

            if i == 0:
                code = (
                    f'var seq=app.project.sequences[{seq_idx}];'
                    'var v=seq.videoTracks[0].clips[0],a=seq.audioTracks[0].clips[0];var t;'
                    't=v.inPoint;t.ticks="'+in_t+'";v.inPoint=t;'
                    't=v.outPoint;t.ticks="'+out_t+'";v.outPoint=t;'
                    't=v.end;t.ticks="'+str(end_t)+'";v.end=t;'
                    't=a.inPoint;t.ticks="'+in_t+'";a.inPoint=t;'
                    't=a.outPoint;t.ticks="'+out_t+'";a.outPoint=t;'
                    't=a.end;t.ticks="'+str(end_t)+'";a.end=t;'
                    'return "OK: in="+v.inPoint.seconds+" out="+v.outPoint.seconds+" @ "+v.start.seconds+"-"+v.end.seconds;'
                )
            else:
                pos_sec = pos_ticks / GRAN
                code = (
                    f'var seq=app.project.sequences[{seq_idx}];'
                    f'var clip=app.project.rootItem.children[{src_idx}];'
                    f'seq.videoTracks[0].insertClip(clip,{pos_sec});'
                    f'seq.audioTracks[0].insertClip(clip,{pos_sec});'
                    f'var v=seq.videoTracks[0].clips[{i}];'
                    f'var a=seq.audioTracks[0].clips[{i}];var t;'
                    't=v.inPoint;t.ticks="'+in_t+'";v.inPoint=t;'
                    't=v.outPoint;t.ticks="'+out_t+'";v.outPoint=t;'
                    't=v.end;t.ticks="'+str(end_t)+'";v.end=t;'
                    'if(a){'
                    't=a.inPoint;t.ticks="'+in_t+'";a.inPoint=t;'
                    't=a.outPoint;t.ticks="'+out_t+'";a.outPoint=t;'
                    't=a.end;t.ticks="'+str(end_t)+'";a.end=t;'
                    '}'
                    'return "OK: in="+v.inPoint.seconds+" out="+v.outPoint.seconds+" @ "+v.start.seconds+"-"+v.end.seconds;'
                )
            r = _exec(bridge, code)
            ok = r.startswith("OK:")
            print(f'  {"  ✓" if ok else "  ✗"} {GREEN if ok else RED}{r[:90]}{RESET}')
            if ok:
                pos_ticks = end_t
    else:
        seq_idx = int(r[3:])
        print(f"  → {SEQ_NAME} @ sequences[{seq_idx}] ({n} clips)")

        # ── 4a) 无 insertClip — 直接设置每段 clip 的 start/end/in/out ──
        print(f"\n  {CYAN}[4/5] 剪辑 (零插入 模式){RESET}")

        pos_ticks = 0
        for i, e in enumerate(edits):
            label = e.get("label", f"seg{i}")
            in_t = _ticks(e["in_point"])
            out_t = _ticks(e["out_point"])
            dur_t = int(out_t) - int(in_t)
            end_t = pos_ticks + dur_t
            start_ticks = str(pos_ticks)
            end_ticks = str(end_t)
            say("CUT", f"[{i+1}/{n}] {label}  {e['in_point']}s→{e['out_point']}s T={round(pos_ticks/GRAN,1)}s")

            code = (
                f'var seq=app.project.sequences[{seq_idx}];'
                f'var v=seq.videoTracks[0].clips[{i}];'
                f'var a=seq.audioTracks[0].clips[{i}];var t;'
                # 先设 start (定位)
                't=v.start;t.ticks="'+start_ticks+'";v.start=t;'
                't=a.start;t.ticks="'+start_ticks+'";a.start=t;'
                # 再设 end (控制时长)
                't=v.end;t.ticks="'+end_ticks+'";v.end=t;'
                't=a.end;t.ticks="'+end_ticks+'";a.end=t;'
                # 再设 in/out (源范围)
                't=v.inPoint;t.ticks="'+in_t+'";v.inPoint=t;'
                't=v.outPoint;t.ticks="'+out_t+'";v.outPoint=t;'
                't=a.inPoint;t.ticks="'+in_t+'";a.inPoint=t;'
                't=a.outPoint;t.ticks="'+out_t+'";a.outPoint=t;'
                'return "OK: in="+v.inPoint.seconds+" out="+v.outPoint.seconds+" @ "+v.start.seconds+"-"+v.end.seconds;'
            )
            r = _exec(bridge, code)
            ok = r.startswith("OK:")
            print(f'  {"  ✓" if ok else "  ✗"} {GREEN if ok else RED}{r[:90]}{RESET}')
            if ok:
                pos_ticks = end_t

    # ── 5) 验证 ──
    print(f"\n  {CYAN}[5/5] 验证{RESET}")
    r = bridge.execute(
        '(function(){'
        '  try {'
        f'    var vt=app.project.sequences[{seq_idx}].videoTracks[0];'
        '    var lines=["总剪辑 "+vt.clips.numItems];'
        '    for(var c=0;c<vt.clips.numItems;c++){'
        '      var cl=vt.clips[c];'
        '      lines.push("  #"+c+" "+cl.name+" start="+Math.round(cl.start.seconds)+"s end="+Math.round(cl.end.seconds)+"s in="+Math.round(cl.inPoint.seconds)+"s out="+Math.round(cl.outPoint.seconds)+"s");'
        '    }'
        '    return lines.join("|");'
        '  } catch(e){return "ERR:"+e.toString();}'
        '})()'
    )
    for p in r.split("|"):
        print(f'  {p}')

    print(f"\n  {GREEN}{'=' * 48}{RESET}")
    print(f"  {GREEN}✓ AI 导演粗剪完成!{RESET}")
    print(f"  {'=' * 48}")
    return True


if __name__ == "__main__":
    edits = DEMO_EDITS
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for e in edits:
        e["file"] = os.path.join(base, e["file"])
    run(edits)
