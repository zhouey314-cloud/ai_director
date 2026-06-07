"""
视频渲染模块 - SRT / EDL / 最终成片
"""
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 时间码工具函数
# ---------------------------------------------------------------------------

def _srt_ts(seconds: float) -> str:
    """秒 → SRT 时间戳  HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def _edl_ts(seconds: float, fps: float = 30.0) -> str:
    """秒 → EDL 时间码  HH:MM:SS:FF"""
    total = int(seconds * fps)
    fr = int(fps)
    h = total // (3600 * fr)
    r = total % (3600 * fr)
    m = r // (60 * fr)
    r = r % (60 * fr)
    s = r // fr
    f = r % fr
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


# ---------------------------------------------------------------------------
# SRT 字幕
# ---------------------------------------------------------------------------

def generate_srt(
    transcript: Optional[Dict[str, Any]],
    keep_segments: List[Tuple[float, float]],
    output_path: str,
) -> Optional[str]:
    """根据保留片段范围生成 SRT 字幕。

    只输出完全落在保留片段内的字幕条目。
    """
    if not transcript:
        print("⚠ 无转写数据，跳过 SRT 生成")
        return None

    entries: List[Tuple[float, float, str]] = []
    for seg in transcript.get("segments", []):
        s = seg["start"]
        e = seg["end"]
        text = seg["text"].strip()
        if not text:
            continue
        for ks, ke in keep_segments:
            if s >= ks and e <= ke:
                entries.append((s, e, text))
                break
            # 部分重叠：仅保留重叠 > 0.5s 的
            overlap_start = max(s, ks)
            overlap_end = min(e, ke)
            if overlap_end - overlap_start > 0.5:
                entries.append((overlap_start, overlap_end, text))
                break

    with open(output_path, "w", encoding="utf-8") as f:
        for i, (s, e, text) in enumerate(entries, 1):
            f.write(f"{i}\n{_srt_ts(s)} --> {_srt_ts(e)}\n{text}\n\n")

    print(f"  生成 SRT: {output_path} ({len(entries)} 条字幕)")
    return output_path


# ---------------------------------------------------------------------------
# DaVinci Resolve EDL (CMX3600)
# ---------------------------------------------------------------------------

def generate_edl(
    keep_segments: List[Tuple[float, float]],
    source_path: str,
    output_path: str,
    fps: float = 30.0,
) -> str:
    """生成 CMX3600 EDL，兼容 DaVinci Resolve 导入。"""
    source_name = os.path.basename(source_path)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("TITLE: AI Director Auto-Edited Sequence\n")
        f.write("FCM: NON-DROP FRAME\n\n")

        tc = 0.0
        for i, (s, e) in enumerate(keep_segments, 1):
            dur = e - s
            f.write(
                f"{i:03d}  AX       V     C        "
                f"{_edl_ts(s, fps)} {_edl_ts(e, fps)} "
                f"{_edl_ts(tc, fps)} {_edl_ts(tc + dur, fps)}\n"
            )
            f.write(f"* FROM CLIP NAME: {source_name}\n\n")
            tc += dur

    print(f"  生成 EDL: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# 最终成片渲染
# ---------------------------------------------------------------------------

def render_final_video(
    video_path: str,
    keep_segments: List[Tuple[float, float]],
    srt_path: Optional[str],
    output_path: str = "output_final.mp4",
    temp_dir: str = ".temp_clips",
) -> str:
    """截取保留片段 → 无缝拼接 → 嵌入软字幕。

    流程: 逐段截取 (重编码保证帧精确) → concat demuxer 合并 → 压入 mov_text 字幕。
    """
    os.makedirs(temp_dir, exist_ok=True)

    clip_paths: List[str] = []
    concat_list = os.path.join(temp_dir, "concat_list.txt")

    try:
        # 1. 逐段截取（重编码确保帧精确）
        print("  正在截取保留片段 ...")
        for i, (s, e) in enumerate(keep_segments):
            dur = e - s
            clip = os.path.join(temp_dir, f"clip_{i:04d}.mp4")
            subprocess.run(
                [
                    "ffmpeg",
                    "-ss", str(s),
                    "-i", video_path,
                    "-t", str(dur),
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    "-y",
                    clip,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            clip_paths.append(clip)

        # 2. 写入 concat 清单
        with open(concat_list, "w") as f:
            for clip in clip_paths:
                f.write(f"file '{os.path.abspath(clip)}'\n")

        # 3. concat 合并（不重编码，直接 copy 流）
        merged = os.path.join(temp_dir, "_merged.mp4")
        subprocess.run(
            [
                "ffmpeg", "-f", "concat",
                "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                "-y",
                merged,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        # 4. 嵌入软字幕（仅当 SRT 非空时才嵌入）
        if srt_path and os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
            subprocess.run(
                [
                    "ffmpeg", "-i", merged,
                    "-i", srt_path,
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    "-c:s", "mov_text",
                    "-metadata:s:s:0", "language=chi",
                    "-y",
                    output_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            # 无字幕则直接 rename
            os.replace(merged, output_path)

        print(f"  生成视频: {output_path}")
        return output_path

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
