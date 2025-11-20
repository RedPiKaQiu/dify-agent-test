"""
Dify Agent 测试工具模块
独立于后端应用，提供构建 Dify API 请求所需的工具函数
"""

from datetime import datetime
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# 任务分类定义（独立于后端枚举）
TASK_CATEGORIES = {
    1: "生活",
    2: "健康",
    3: "工作",
    4: "学习",
    5: "放松",
    6: "探索",
}

# 任务重复频率定义（独立于后端枚举）
REPETITION_LABELS = {
    0: "不重复",
    1: "每日",
    2: "每周",
    3: "每月",
}


def build_category_string() -> str:
    """
    生成任务分类字符串供AI使用
    
    Returns:
        str: 格式化的分类字符串，如 "1：生活/2：健康/..."
    """
    categories = [
        f"{value}：{description}"
        for value, description in sorted(TASK_CATEGORIES.items())
    ]
    return "/".join(categories)


def build_repetition_string() -> str:
    """
    生成任务重复频率字符串供AI使用
    
    Returns:
        str: 格式化的重复频率字符串，如 "0：不重复/1：每日/..."
    """
    repetitions = [
        f"{value}：{label}"
        for value, label in sorted(REPETITION_LABELS.items())
    ]
    return "/".join(repetitions)


def build_nowtime(timezone: Optional[str] = None) -> str:
    """
    统一构建nowtime参数，返回ISO格式字符串
    
    Args:
        timezone: 时区字符串，如 'Asia/Shanghai'，默认为 None（使用系统时区）
        
    Returns:
        str: ISO格式的时间字符串
    """
    try:
        if timezone:
            tz = ZoneInfo(timezone)
            current_time = datetime.now(tz)
        else:
            current_time = datetime.now()
        return current_time.isoformat()
    except ZoneInfoNotFoundError:
        # 如果时区无效，使用系统时区
        return datetime.now().isoformat()


def get_context_info(timezone: Optional[str] = None) -> Dict[str, Any]:
    """
    获取环境上下文信息（简化版，独立实现）
    
    Args:
        timezone: 时区字符串，如 'Asia/Shanghai'，默认为 None（使用系统时区）
        
    Returns:
        Dict: 包含 time_of_day, day_of_week, season 的字典
    """
    try:
        if timezone:
            tz = ZoneInfo(timezone)
            current_time = datetime.now(tz)
        else:
            current_time = datetime.now()
    except ZoneInfoNotFoundError:
        current_time = datetime.now()
    
    # 获取时间段
    hour = current_time.hour
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "night"
    
    # 获取星期几
    days = [
        "Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday"
    ]
    day_of_week = days[current_time.weekday()]
    
    # 获取季节（北半球）
    month = current_time.month
    if month in [12, 1, 2]:
        season = "winter"
    elif month in [3, 4, 5]:
        season = "spring"
    elif month in [6, 7, 8]:
        season = "summer"
    else:  # [9, 10, 11]
        season = "autumn"
    
    return {
        "time_of_day": time_of_day,
        "day_of_week": day_of_week,
        "weather": None,  # 暂时不包含天气信息
        "season": season
    }


def format_response(answer: str, conversation_id: Optional[str] = None, 
                   metadata: Optional[Dict[str, Any]] = None,
                   response_time: Optional[float] = None) -> str:
    """
    格式化AI响应用于显示
    
    Args:
        answer: AI返回的答案
        conversation_id: 对话ID
        metadata: 元数据（包含token使用量等信息）
        response_time: API响应时间（秒）
        
    Returns:
        str: 格式化后的响应字符串
    """
    lines = []
    lines.append("=" * 60)
    lines.append("AI 响应:")
    lines.append("-" * 60)
    lines.append(answer)
    lines.append("-" * 60)
    
    if conversation_id:
        lines.append(f"对话ID: {conversation_id}")
    
    if response_time is not None:
        lines.append(f"响应时间: {response_time:.2f} 秒")
    
    if metadata:
        usage = metadata.get("usage", {})
        if usage:
            total_tokens = usage.get("total_tokens")
            if total_tokens:
                lines.append(f"Token 使用量: {total_tokens}")
        
        model = metadata.get("model")
        if model:
            lines.append(f"模型: {model}")
    
    lines.append("=" * 60)
    return "\n".join(lines)

