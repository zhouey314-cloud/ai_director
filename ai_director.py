#!/usr/bin/env python3
"""
AI Director - 个人口播视频自动化剪辑工具
=============================================

工作流:
  1. 音频提取 + 静音检测 (ffmpeg silencedetect)
  2. AI 语音转写 (Whisper API) + AI 语义精简 (DeepSeek API, 可选)
  3. 渲染输出: SRT / EDL / 最终 MP4

用法:
  python ai_director.py input.mp4 [选项]

环境变量:
  WHISPER_API_KEY    OpenAI 兼容格式的 Whisper API 密钥 (可选，留空则使用本地 faster-whisper)
  DEEPSEEK_API_KEY   DeepSeek API 密钥 (可选，用于智能语义精简)
  WHISPER_BASE_URL   Whisper 兼容端点地址 (可选，默认 https://api.openai.com/v1)

依赖:
  - macOS / Linux (已测试)
  - ffmpeg (需预先安装)
  - pip install openai>=1.0.0

示例:
  export WHISPER_API_KEY="sk-xxx"
  export DEEPSEEK_API_KEY="sk-yyy"

  python ai_director.py input.mp4
  python ai_director.py input.mp4 --silence-only
  python ai_director.py input.mp4 --threshold -35 --min-silence 0.8
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

from modules.audio_processor import extract_audio, detect_silence, get_audio_duration
from modules.ai_services import transcribe_audio, analyze_transcript
from modules.timeline_editor import merge_silence_and_ai_cuts
from modules.video_renderer import generate_srt, generate_edl, generate_fcpxml, render_final_video


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ai_director.py",
        description="AI Director - 个人口播视频自动化剪辑工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
环境变量:
  WHISPER_API_KEY     OpenAI 兼容 Whisper API 密钥 (必填)
  DEEPSEEK_API_KEY    DeepSeek API 密钥 (推荐，用于智能语义精简)
  WHISPER_BASE_URL    Whisper 兼容端点地址 (可选)

示例:
  python ai_director.py input.mp4
  python ai_director.py input.mp4 --silence-only
  python ai_director.py input.mp4 -o ./output --threshold -35
        """,
    )
    p.add_argument("input", help="输入视频文件路径")
    p.add_argument("-o", "--output-dir", default="./output", help="输出目录 (默认 ./output)")
    p.add_argument("--threshold", type=int, default=-30, help="静音阈值 dB (默认 -30)")
    p.add_argument("--min-silence", type=float, default=0.6, help="最小静音持续秒数 (默认 0.6)")
    p.add_argument("--silence-only", action="store_true", help="仅静音检测，跳过 AI 转写与分析")
    p.add_argument("--skip-ai-cuts", action="store_true", help="跳过 DeepSeek 语义分析 (保留转写)")
    p.add_argument("--whisper-model", default="whisper-1", help="Whisper 模型 — 线上: whisper-1，本地: base/small/medium/large-v3 (默认 whisper-1 → 本地映射为 base)")
    p.add_argument("--deepseek-model", default="deepseek-v4-flash", help="DeepSeek 模型")
    p.add_argument("--fps", type=float, default=30.0, help="EDL 帧率 (默认 30)")
    p.add_argument("--no-srt", action="store_true", help="不生成字幕")
    p.add_argument("--no-edl", action="store_true", help="不生成 EDL")
    p.add_argument("--no-fcpxml", action="store_true", help="不生成 FCPXML（Premiere Pro 用）")
    p.add_argument("--no-video", action="store_true", help="不渲染成片")
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    input_path = args.input
    if not os.path.isfile(input_path):
        print(f"❌ 文件不存在: {input_path}")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(input_path))[0]

    print("=" * 56)
    print("  AI Director — 口播视频自动化剪辑")
    print(f"  输入: {input_path}")
    print("=" * 56)

    # ---- Step 1: 音频提取 + 静音检测 ----
    print("\n[1/4] 音频提取与静音检测")
    audio_path = extract_audio(input_path, os.path.join(args.output_dir, f"{base}_audio.wav"))
    total_dur = get_audio_duration(audio_path)
    print(f"  音频时长: {total_dur:.1f}s")

    silent = detect_silence(audio_path, threshold=args.threshold, min_duration=args.min_silence)
    print(f"  检测到 {len(silent)} 个静音片段")

    # ---- Step 2: AI 转写 + 语义分析 ----
    transcript: Optional[Dict[str, Any]] = None
    ai_cuts: List[Tuple[float, float, str]] = []

    if not args.silence_only:
        print("\n[2/4] AI 语音转写与语义精简")

        try:
            transcript = transcribe_audio(
                audio_path,
                api_key=os.getenv("WHISPER_API_KEY"),
                base_url=os.getenv("WHISPER_BASE_URL"),
                model=args.whisper_model,
            )
            preview = transcript["text"][:80]
            print(f"  转写预览: {preview}...")
            print(f"  共 {len(transcript['segments'])} 个语义段")

            # 保存转写结果
            json_path = os.path.join(args.output_dir, f"{base}_transcript.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(transcript, f, ensure_ascii=False, indent=2)
            print(f"  转写已保存: {json_path}")

            # DeepSeek 分析
            if not args.skip_ai_cuts:
                ai_cuts = analyze_transcript(
                    transcript,
                    api_key=os.getenv("DEEPSEEK_API_KEY"),
                    model=args.deepseek_model,
                )
            else:
                print("  跳过 DeepSeek 语义分析")

        except Exception as exc:
            print(f"⚠ AI 处理失败: {exc}")
            print("  回退到仅静音模式")

    # ---- Step 3: 合并决策，生成保留片段 ----
    print("\n[3/4] 生成保留片段列表")
    keeps = merge_silence_and_ai_cuts(silent, ai_cuts, total_dur)

    if not keeps:
        print("❌ 没有保留任何片段，请检查视频或调低阈值")
        sys.exit(1)

    # 保存 keep list 供复查
    keep_path = os.path.join(args.output_dir, f"{base}_keep_list.json")
    with open(keep_path, "w", encoding="utf-8") as f:
        json.dump([{"start": s, "end": e} for s, e in keeps], f, ensure_ascii=False, indent=2)
    print(f"  保留列表已保存: {keep_path}")

    # ---- Step 4: 输出 ----
    print("\n[4/4] 渲染输出文件")

    srt_path: Optional[str] = None
    if not args.no_srt and transcript:
        srt_path = generate_srt(
            transcript,
            keeps,
            os.path.join(args.output_dir, f"{base}_subtitles.srt"),
        )

    if not args.no_edl:
        generate_edl(
            keeps,
            input_path,
            os.path.join(args.output_dir, f"{base}_davinci.edl"),
            fps=args.fps,
        )

    if not args.no_fcpxml:
        generate_fcpxml(
            keeps,
            input_path,
            os.path.join(args.output_dir, f"{base}_premiere.fcpxml"),
            fps=args.fps,
            total_duration=total_dur,
        )

    if not args.no_video:
        render_final_video(
            input_path,
            keeps,
            srt_path,
            os.path.join(args.output_dir, f"{base}_final.mp4"),
        )

    print("\n" + "=" * 56)
    print("  ✅ 处理完成！")
    print(f"  输出目录: {os.path.abspath(args.output_dir)}")
    print("=" * 56)


if __name__ == "__main__":
    main()
