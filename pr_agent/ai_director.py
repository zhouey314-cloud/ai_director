#!/usr/bin/env python3
"""
ai_director.py — AI 导演剪辑控制器

零 insertClip 方案 + 可选 Whisper 自动字幕.
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

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
    return bridge.execute(
        '(function(){ try { ' + code + ' } catch(e){return "ERROR:"+e.toString().substring(0,200);} })()'
    )


def _srt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


# ──────────────────────────────────────────────
# 自动字幕
# ──────────────────────────────────────────────

def _map_to_timeline(segments: list[dict], edits: list[dict]) -> list[tuple]:
    """将 Whisper 源时间 segments 映射到时间线坐标.

    每条 edit 定义了源到时间线的映射:
        edit[i]: source[in_point, out_point] → timeline[pos, pos+duration]
    """
    # 构建 edit 映射表
    timeline_pos = 0.0
    edit_map = []
    for e in edits:
        dur = e["out_point"] - e["in_point"]
        edit_map.append({
            "src_s": e["in_point"], "src_e": e["out_point"],
            "tl_s": timeline_pos, "tl_e": timeline_pos + dur,
        })
        timeline_pos += dur

    mapped = []
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        ss, se = seg["start"], seg["end"]
        for em in edit_map:
            if ss >= em["src_s"] and se <= em["src_e"]:
                ts = em["tl_s"] + (ss - em["src_s"])
                te = em["tl_s"] + (se - em["src_s"])
                mapped.append((ts, te, text))
                break
            elif ss >= em["src_s"] and ss < em["src_e"]:
                ts = em["tl_s"] + (ss - em["src_s"])
                mapped.append((ts, em["tl_e"], text))
                break
    return mapped


def _write_srt(segments: list[tuple], output_path: str) -> str:
    """写入时间线坐标 SRT"""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, (s, e, text) in enumerate(segments, 1):
            f.write(f"{i}\n{_srt_ts(s)} --> {_srt_ts(e)}\n{text}\n\n")
    return output_path


def generate_subtitles(edits: list[dict], source_file: str, seq_idx: int,
                       bridge, output_dir: str, render_video: bool = False) -> str | None:
    """Whisper 转写 → 时间映射 → SRT → PR 导入 → 可选硬字幕渲染"""
    print(f"\n  {CYAN}[5/6] 自动字幕{RESET}")

    # 动态导入 (失败时不阻塞主流程)
    try:
        from modules.audio_processor import extract_audio
        from modules.ai_services import transcribe_audio
    except ImportError as e:
        print(f"  {YELLOW}⚠ 模块导入失败: {e}{RESET}")
        print(f"  {YELLOW}  跳过字幕生成{RESET}")
        return None

    # 1) 提取音频
    audio_path = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(source_file))[0]}_audio.wav")
    if not os.path.exists(audio_path):
        print(f"  提取音频...")
        try:
            audio_path = extract_audio(source_file, audio_path)
            dur = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                capture_output=True, text=True, check=True
            )
            print(f"  音频: {float(dur.stdout.strip()):.1f}s")
        except Exception as e:
            print(f"  {YELLOW}⚠ 音频提取失败: {e}{RESET}")
            return None
    else:
        print(f"  复用已有音频: {audio_path}")

    # 2) Whisper 转写
    print(f"  语音转写中 (首次加载模型约需1-2分钟)...")
    try:
        transcript = transcribe_audio(audio_path)
        print(f"  转写完成: {len(transcript.get('segments', []))} 个语义段")
        preview = transcript.get("text", "")[:80]
        if preview:
            print(f"  预览: {preview}...")
    except Exception as e:
        print(f"  {YELLOW}⚠ 转写失败: {e}{RESET}")
        return None

    # 3) 时间映射
    raw_segments = transcript.get("segments", [])
    mapped = _map_to_timeline(raw_segments, edits)
    print(f"  映射到时间线: {len(mapped)} 条字幕")
    if mapped:
        first, last = mapped[0], mapped[-1]
        print(f"  范围: T={first[0]:.1f}s → T={last[1]:.1f}s")

    # 4) 写 SRT
    os.makedirs(output_dir, exist_ok=True)
    srt_path = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(source_file))[0]}_subtitles.srt")
    _write_srt(mapped, srt_path)
    print(f"  SRT: {srt_path}")

    # 5) 导入 PR
    try:
        r = bridge.execute(
            f'app.project.importFiles([{json.dumps(srt_path)}], true, app.project.rootItem, false);'
        )
        print(f"  {'  ✓' if r == 'true' else '  ✗'} PR 导入: {r}")
    except Exception as e:
        print(f"  {YELLOW}⚠ PR 导入失败: {e}{RESET}")

    # 6) 可选: ffmpeg 硬字幕渲染
    if render_video:
        print(f"\n  渲染带字幕视频...")
        try:
            _render_with_subtitles(edits, source_file, srt_path, output_dir)
        except Exception as e:
            print(f"  {YELLOW}⚠ 视频渲染失败: {e}{RESET}")

    return srt_path


def _render_with_subtitles(edits, source_file, srt_path, output_dir):
    """用 ffmpeg 截取编辑段 + 烧录硬字幕"""
    base = os.path.splitext(os.path.basename(source_file))[0]
    temp_dir = os.path.join(output_dir, ".temp_sub_clips")
    os.makedirs(temp_dir, exist_ok=True)

    clip_paths = []
    concat_list = os.path.join(temp_dir, "concat_list.txt")
    try:
        # 逐段截取
        for i, e in enumerate(edits):
            dur = e["out_point"] - e["in_point"]
            clip = os.path.join(temp_dir, f"clip_{i:04d}.mp4")
            subprocess.run([
                "ffmpeg", "-ss", str(e["in_point"]), "-i", source_file,
                "-t", str(dur),
                "-c:v", "libx264", "-c:a", "aac",
                "-preset", "fast", "-pix_fmt", "yuv420p", "-y", clip,
            ], check=True, capture_output=True, text=True)
            clip_paths.append(clip)

        # concat 清单
        with open(concat_list, "w") as f:
            for clip in clip_paths:
                f.write(f"file '{os.path.abspath(clip)}'\n")

        merged = os.path.join(temp_dir, "_merged.mp4")
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", concat_list, "-c", "copy", "-y", merged,
        ], check=True, capture_output=True, text=True)

        # 烧录硬字幕
        final = os.path.join(output_dir, f"{base}_final.mp4")
        if os.path.getsize(srt_path) > 0:
            subprocess.run([
                "ffmpeg", "-i", merged, "-i", srt_path,
                "-c:v", "libx264", "-c:a", "aac",
                "-preset", "fast", "-pix_fmt", "yuv420p",
                "-vf", f"subtitles={srt_path}",
                "-y", final,
            ], check=True, capture_output=True, text=True)
        else:
            os.replace(merged, final)

        print(f"  → {final}")
    finally:
        for clip in clip_paths:
            try:
                os.remove(clip)
            except OSError:
                pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass


# ──────────────────────────────────────────────
# 主管线
# ──────────────────────────────────────────────

def run(edits: list[dict], subtitles: bool = False, render_video: bool = False):
    bridge = PrJsxBridge()
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    steps = "6" if subtitles else "5"

    print(f"\n  {BOLD}AI 导演 — 最终工作流{RESET}")
    print(f"  {'=' * 48}")
    print(f"  指令: {len(edits)}  序列: {SEQ_NAME}")
    if subtitles:
        print(f"  字幕: Whisper 自动转写 + 时间映射")
    print()

    # ── 1) 项目 ──
    print(f"  {CYAN}[1/{steps}] 项目{RESET}")
    if not bridge.is_project_open():
        print(f"  {YELLOW}⚠ 需要打开项目{RESET}")
        return False
    print(f"  → {bridge.get_project_name()}")

    # ── 2) 素材 ──
    print(f"\n  {CYAN}[2/{steps}] 素材{RESET}")
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
    source_file = os.path.join(base_dir, first_file)

    # ── 3) 创建序列 ──
    print(f"\n  {CYAN}[3/{steps}] 创建序列{RESET}")
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
        print(f"  {YELLOW}⚠ 回退到 insertClip 方案...{RESET}")
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

        print(f"\n  {CYAN}[4/{steps}] 剪辑 (insertClip 模式){RESET}")
        pos_ticks = 0
        for i, e in enumerate(edits):
            in_t = _ticks(e["in_point"])
            out_t = _ticks(e["out_point"])
            dur_t = int(out_t) - int(in_t)
            end_t = pos_ticks + dur_t
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
                    'return "OK: "+v.start.seconds+"-"+v.end.seconds+"s in="+v.inPoint.seconds+" out="+v.outPoint.seconds;'
                )
            else:
                pos_sec = pos_ticks / GRAN
                code = (
                    f'var seq=app.project.sequences[{seq_idx}];'
                    f'var clip=app.project.rootItem.children[{src_idx}];'
                    f'seq.videoTracks[0].insertClip(clip,{pos_sec});'
                    f'seq.audioTracks[0].insertClip(clip,{pos_sec});'
                    f'var v=seq.videoTracks[0].clips[{i}];var a=seq.audioTracks[0].clips[{i}];var t;'
                    't=v.inPoint;t.ticks="'+in_t+'";v.inPoint=t;'
                    't=v.outPoint;t.ticks="'+out_t+'";v.outPoint=t;'
                    't=v.end;t.ticks="'+str(end_t)+'";v.end=t;'
                    'if(a){t=a.inPoint;t.ticks="'+in_t+'";a.inPoint=t;'
                    't=a.outPoint;t.ticks="'+out_t+'";a.outPoint=t;'
                    't=a.end;t.ticks="'+str(end_t)+'";a.end=t;}'
                    'return "OK: "+v.start.seconds+"-"+v.end.seconds+"s";'
                )
            r = _exec(bridge, code)
            ok = r.startswith("OK:")
            say("CUT", f"[{i+1}/{n}] {e.get('label',f'seg{i}')}  {e['in_point']}s→{e['out_point']}s T={round(pos_ticks/GRAN,1)}s")
            print(f'  {"  ✓" if ok else "  ✗"} {GREEN if ok else RED}{r[:90]}{RESET}')
            if ok:
                pos_ticks = end_t
    else:
        seq_idx = int(r[3:])
        print(f"  → {SEQ_NAME} @ sequences[{seq_idx}] ({n} clips)")

        print(f"\n  {CYAN}[4/{steps}] 剪辑 (零插入 模式){RESET}")
        pos_ticks = 0
        for i, e in enumerate(edits):
            in_t = _ticks(e["in_point"])
            out_t = _ticks(e["out_point"])
            dur_t = int(out_t) - int(in_t)
            end_t = pos_ticks + dur_t
            code = (
                f'var seq=app.project.sequences[{seq_idx}];'
                f'var v=seq.videoTracks[0].clips[{i}];'
                f'var a=seq.audioTracks[0].clips[{i}];var t;'
                't=v.start;t.ticks="'+str(pos_ticks)+'";v.start=t;'
                't=a.start;t.ticks="'+str(pos_ticks)+'";a.start=t;'
                't=v.end;t.ticks="'+str(end_t)+'";v.end=t;'
                't=a.end;t.ticks="'+str(end_t)+'";a.end=t;'
                't=v.inPoint;t.ticks="'+in_t+'";v.inPoint=t;'
                't=v.outPoint;t.ticks="'+out_t+'";v.outPoint=t;'
                't=a.inPoint;t.ticks="'+in_t+'";a.inPoint=t;'
                't=a.outPoint;t.ticks="'+out_t+'";a.outPoint=t;'
                'return "OK: "+v.start.seconds+"-"+v.end.seconds+"s in="+v.inPoint.seconds+" out="+v.outPoint.seconds;'
            )
            r = _exec(bridge, code)
            ok = r.startswith("OK:")
            say("CUT", f"[{i+1}/{n}] {e.get('label',f'seg{i}')}  {e['in_point']}s→{e['out_point']}s T={round(pos_ticks/GRAN,1)}s")
            print(f'  {"  ✓" if ok else "  ✗"} {GREEN if ok else RED}{r[:90]}{RESET}')
            if ok:
                pos_ticks = end_t

    # ── 5) 验证 ──
    print(f"\n  {CYAN}[5/{steps}] 验证{RESET}")
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

    # ── 6) 自动字幕 (可选) ──
    srt_path = None
    if subtitles:
        output_dir = os.path.join(base_dir, "output")
        srt_path = generate_subtitles(edits, source_file, seq_idx, bridge, output_dir, render_video)

    print(f"\n  {GREEN}{'=' * 48}{RESET}")
    print(f"  {GREEN}✓ AI 导演粗剪完成!{RESET}")
    if srt_path:
        print(f"  {GREEN}✓ 字幕: {srt_path}{RESET}")
    print(f"  {'=' * 48}")
    return True


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="AI Director - PR 自动粗剪 + 字幕")
    p.add_argument("--subtitles", "-s", action="store_true", help="启用 Whisper 自动字幕")
    p.add_argument("--render", "-r", action="store_true", help="渲染带硬字幕的 MP4 (需 --subtitles)")
    p.add_argument("--edits", "-e", type=str, help="编辑指令 JSON 文件路径 (默认演示数据)")
    args = p.parse_args()

    if args.edits:
        with open(args.edits, encoding="utf-8") as f:
            edits = json.load(f)
    else:
        edits = DEMO_EDITS

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for e in edits:
        e["file"] = os.path.join(base, e["file"])
    run(edits, subtitles=args.subtitles, render_video=args.render)
