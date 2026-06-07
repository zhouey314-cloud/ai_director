"""
AI 服务模块 - Whisper 语音转写 & DeepSeek 语义分析
"""
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# ---------------------------------------------------------------------------
# 本地 faster-whisper 模型缓存
# ---------------------------------------------------------------------------

_LOCAL_WHISPER_MODEL = None


def _get_local_model(model_name: str) -> Any:
    """懒加载本地 faster-whisper 模型（模块级缓存，避免重复加载）"""
    global _LOCAL_WHISPER_MODEL
    if _LOCAL_WHISPER_MODEL is None:
        from faster_whisper import WhisperModel

        print(f"  正在加载本地语音模型 ({model_name})，首次下载可能需要几分钟...")
        _LOCAL_WHISPER_MODEL = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _LOCAL_WHISPER_MODEL


# ---------------------------------------------------------------------------
# Whisper 语音转写（自动选择 线上 API / 本地模型）
# ---------------------------------------------------------------------------

def transcribe_audio(
    audio_path: str,
    api_key: str = None,
    base_url: str = None,
    model: str = "whisper-1",
    language: str = "zh",
) -> Dict[str, Any]:
    """将音频转写为带时间戳的文本。

    自动选择模式：
      - 提供了 WHISPER_API_KEY       → 调用线上 Whisper 兼容 API
      - 未提供 WHISPER_API_KEY       → 使用本地 faster-whisper 模型

    两种模式返回格式完全一致：
        { "text": str, "segments": [{"start": float, "end": float, "text": str}] }

    Args:
        audio_path: 音频文件路径
        api_key: API key（默认从 WHISPER_API_KEY 环境变量读取）
        base_url: 兼容端点的 base URL（仅线上模式生效）
        model: 模型名（线上默认 whisper-1，本地默认 base）
        language: 语言代码
    """
    api_key = api_key or os.getenv("WHISPER_API_KEY")

    if api_key:
        return _transcribe_via_api(audio_path, api_key, base_url, model, language)
    else:
        return _transcribe_via_local(audio_path, model, language)


def _transcribe_via_api(
    audio_path: str,
    api_key: str,
    base_url: str | None,
    model: str,
    language: str,
) -> Dict[str, Any]:
    """线上 Whisper API 转写"""
    client = OpenAI(api_key=api_key, **( {"base_url": base_url} if base_url else {} ))

    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=model,
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            language=language,
        )

    segments = []
    for seg in resp.segments:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        })

    return {
        "text": resp.text or "",
        "segments": segments,
    }


def _transcribe_via_local(
    audio_path: str,
    model: str,
    language: str,
) -> Dict[str, Any]:
    """本地 faster-whisper 转写"""
    # 将 API 默认模型名映射为本地模型大小
    local_model = "base" if model == "whisper-1" else model

    whisper = _get_local_model(local_model)
    segments_gen, info = whisper.transcribe(
        audio_path,
        language=language,
        beam_size=5,
    )

    segments = []
    text_parts = []
    for segment in segments_gen:
        segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
        })
        text_parts.append(segment.text)

    print(f"  本地转写完成 | 检测到语言: {info.language} (概率 {info.language_probability:.2%})")
    return {
        "text": "".join(text_parts),
        "segments": segments,
    }


def format_transcript(transcript: Dict[str, Any]) -> str:
    """将转写结果格式化为带时间戳的文本（供 DeepSeek 阅读）"""
    lines = []
    for seg in transcript.get("segments", []):
        s = seg["start"]
        e = seg["end"]
        t = seg["text"].strip()
        if t:
            lines.append(f"[{s:.2f}-{e:.2f}] {t}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DeepSeek 语义精简
# ---------------------------------------------------------------------------

DEEPSEEK_SYSTEM_PROMPT = """你是一个专业的视频剪辑师。请阅读以下口播文字稿，找出所有的：

1. **口水音/填充词**：如"嗯"、"啊"、"这个"、"那个"、"就是说"等没有信息量的词汇或句子
2. **重复内容**：同样意思的话反复说
3. **忘词/卡顿**：明显不连贯或语义空缺的片段
4. **逻辑错误或跑题**：与主题无关或逻辑不通的内容

以 JSON 对象格式返回，key 为 "cuts"，value 为删除片段数组。每个片段格式：
- "start": 开始时间（秒）
- "end": 结束时间（秒）
- "reason": 删除原因

如果没有任何需要删除的内容，返回 {"cuts": []}。只返回 JSON，不要额外说明。"""


def analyze_transcript(
    transcript: Dict[str, Any],
    api_key: str = None,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-flash",
) -> List[Tuple[float, float, str]]:
    """调用 DeepSeek 分析口播文稿，返回需删除片段列表。

    Returns:
        [(start, end, reason), ...]  空列表表示跳过（无 key 或调用失败）
    """
    api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("⚠ 未设置 DEEPSEEK_API_KEY，跳过智能语义分析")
        return []

    client = OpenAI(api_key=api_key, base_url=base_url)
    formatted = format_transcript(transcript)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
                {"role": "user", "content": formatted},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
    except Exception as e:
        print(f"⚠ DeepSeek API 调用失败: {e}")
        return []

    content = response.choices[0].message.content or ""

    # 解析 JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r'\[.*?\]', content, re.DOTALL)
        if m:
            try:
                data = {"cuts": json.loads(m.group())}
            except json.JSONDecodeError:
                return []
        else:
            return []

    cuts = data.get("cuts") or data.get("segments") or data.get("result") or []
    results: List[Tuple[float, float, str]] = []
    for item in cuts:
        if isinstance(item, dict):
            s = float(item.get("start", 0))
            e = float(item.get("end", 0))
            reason = item.get("reason", "AI 判定为废话")
            if s < e:
                results.append((s, e, reason))

    print(f"  DeepSeek 建议删除 {len(results)} 个片段")
    return results
