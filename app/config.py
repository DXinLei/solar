"""应用配置：从 config.json 加载可配置项。

- get_default_location()  热读地理位置（带短缓存，飞书修改后即时生效）
- update_default_location()  原子写入地理位置（飞书 SET 指令）
- get_lark_config()        读取飞书应用凭证
- get_reminder_config()    读取提醒规则
"""

import json
import time
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

# 内置兜底默认值
_FALLBACK: dict[str, Any] = {
    "province": "四川省",
    "city": "成都市",
    "district": "双流区",
}

# 热读缓存（避免高频轮询反复 IO）
_default_location_cache: dict[str, Any] | None = None
_last_read_ts: float = 0.0
_CACHE_TTL = 10.0  # 秒


def _load_config() -> dict[str, Any]:
    """读取 config.json，解析 default_location 字段。文件不存在或格式错误时使用兜底值。"""
    if not CONFIG_PATH.exists():
        return dict(_FALLBACK)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        loc = data.get("default_location", {})
        return {
            "province": loc.get("province", _FALLBACK["province"]),
            "city": loc.get("city", _FALLBACK["city"]),
            "district": loc.get("district", _FALLBACK["district"]),
        }
    except (json.JSONDecodeError, OSError):
        return dict(_FALLBACK)


def _load_full_config() -> dict[str, Any]:
    """读取 config.json 完整内容，文件不存在或格式错误时返回空字典。"""
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_default_location() -> dict[str, Any]:
    """读取当前生效的默认地理位置（带短缓存，飞书 SET 修改后最多 10s 生效）。"""
    global _default_location_cache, _last_read_ts
    now = time.time()
    if _default_location_cache is None or (now - _last_read_ts) > _CACHE_TTL:
        _default_location_cache = _load_config()
        _last_read_ts = now
    return _default_location_cache


def update_default_location(province: str, city: str, district: str) -> None:
    """原子写入 config.json 的 default_location，并清缓存使下次读取即时生效。

    实现方式：写入临时文件 → os.replace 原子覆盖 → 清缓存。
    并发安全：Python 的 os.replace 在同文件系统下是原子的。
    """
    import os

    # 保留现有 config.json 中的其他字段
    existing = _load_full_config()
    existing["default_location"] = {"province": province, "city": city, "district": district}

    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    # 原子覆盖
    os.replace(tmp_path, CONFIG_PATH)

    # 清缓存，下次读取时重新加载
    global _default_location_cache, _last_read_ts
    _default_location_cache = None
    _last_read_ts = 0.0


def get_lark_config() -> dict[str, Any]:
    """读取飞书应用配置（app_id, app_secret 等）。"""
    data = _load_full_config()
    lark = data.get("lark", {})
    return {
        "app_id": lark.get("app_id", ""),
        "app_secret": lark.get("app_secret", ""),
        "remind_user_open_id": lark.get("remind_user_open_id", ""),
    }


def get_reminder_config() -> dict[str, Any]:
    """读取定时提醒规则配置。"""
    data = _load_full_config()
    reminder = data.get("reminder", {})
    return {
        "enabled": reminder.get("enabled", True),
        "advance_minutes": reminder.get("advance_minutes", 15),
        "interval_seconds": reminder.get("interval_seconds", 60),
    }


# 向后兼容：服务启动时的初始值（用于 main.py 中的 /api/solar-time 接口）
# 注意：飞书 SET 修改后，此变量不会更新。接口需改用 get_default_location()
default_location = _load_config()
