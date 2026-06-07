"""
时间线编辑模块 - 合并剪辑决策，生成最终保留片段列表
"""
from typing import List, Tuple


def merge_silence_and_ai_cuts(
    silent_segments: List[Tuple[float, float]],
    ai_cuts: List[Tuple[float, float, str]],
    total_duration: float,
    margin: float = 0.1,
    min_keep: float = 0.2,
) -> List[Tuple[float, float]]:
    """合并静音与 AI 删除片段，取反得到保留片段列表。

    Args:
        silent_segments: 静音片段 [(start, end), …]
        ai_cuts: AI 判定删除片段 [(start, end, reason), …]
        total_duration: 视频总时长（秒）
        margin: 相邻删除片段合并容差（秒）
        min_keep: 保留片段最短长度（秒）

    Returns:
        [(start, end), …]  排序后的保留片段
    """
    # 汇集所有删除片段
    removes: List[Tuple[float, float]] = []
    removes.extend(silent_segments)
    for s, e, _ in ai_cuts:
        removes.append((s, e))

    if not removes:
        return [(0.0, total_duration)]

    removes.sort(key=lambda x: x[0])

    # 合并重叠 / 相邻删除片段
    merged: List[List[float]] = []
    for s, e in removes:
        if not merged:
            merged.append([s, e])
        else:
            last = merged[-1]
            if s - last[1] <= margin:
                last[1] = max(last[1], e)
            else:
                merged.append([s, e])

    # 取反 → 保留片段
    keeps: List[Tuple[float, float]] = []
    cursor = 0.0
    for s, e in merged:
        if s - cursor >= min_keep:
            keeps.append((cursor, s))
        cursor = max(cursor, e)

    if total_duration - cursor >= min_keep:
        keeps.append((cursor, total_duration))

    # 统计
    removed_secs = sum(e - s for s, e in merged)
    kept_secs = total_duration - removed_secs
    print(f"  删除 {len(merged)} 个片段，保留 {len(keeps)} 个片段")
    print(f"  删除 {removed_secs:.1f}s | 保留 {kept_secs:.1f}s | 压缩率 {kept_secs/total_duration*100:.0f}%")

    return keeps
