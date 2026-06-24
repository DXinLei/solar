"""应用配置：从 config.json 加载可配置项，启动时一次性读取。"""

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

# 内置兜底默认值
_FALLBACK: dict[str, Any] = {
    "province": "四川省",
    "city": "成都市",
    "district": "双流区",
}


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


default_location = _load_config()
