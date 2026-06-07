"""
音频处理模块 - 音频提取与静音检测
"""
import subprocess
import re
import os
from typing import List, Tuple


def extract_audio(video_path: str, output_path: str = None) -> str:
    """从视频中提取音频 (16kHz 单声道 WAV)

    Args:
        video_path: 输入视频路径
        output_path: 输出音频路径，默认同目录下同名 .wav

    Returns:
        音频文件路径
    """
    if output_path is None:
        output_path = os.path.splitext(video_path)[0] + "_audio.wav"

    cmd = [
        'ffmpeg', '-i', video_path,
        '-vn',
        '-acodec', 'pcm_s16le',
        '-ar', '16000',
        '-ac', '1',
        '-y',
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path


def detect_silence(
    audio_path: str,
    threshold: int = -30,
    min_duration: float = 0.6
) -> List[Tuple[float, float]]:
    """使用 ffmpeg silencedetect 检测静音片段

    Args:
        audio_path: 音频文件路径
        threshold: 静音阈值 (dB)
        min_duration: 最小静音持续秒数

    Returns:
        [(start, end), ...] 静音片段列表
    """
    cmd = [
        'ffmpeg', '-i', audio_path,
        '-af', f'silencedetect=noise={threshold}dB:d={min_duration}',
        '-f', 'null', '-'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr or result.stdout

    starts: List[float] = []
    ends: List[float] = []

    for line in output.split('\n'):
        m = re.search(r'silence_start:\s+([\d.]+)', line)
        if m:
            starts.append(float(m.group(1)))
            continue
        m = re.search(r'silence_end:\s+([\d.]+)', line)
        if m:
            ends.append(float(m.group(1)))

    segments = list(zip(starts, ends))
    if len(starts) > len(ends):
        for s in starts[len(ends):]:
            segments.append((s, s + min_duration))

    return segments


def get_audio_duration(audio_path: str) -> float:
    """获取音频时长 (秒)"""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())
