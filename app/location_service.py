"""
位置管理服务：提供位置查询与更新的统一业务逻辑。

被 HTTP API（POST /api/location）和飞书机器人（/set）共同调用，
更新后自动触发配置原子落盘并重载调度器任务。
"""

from typing import Any
from .config import get_default_location, update_default_location
from .data_loader import loader, AddressNotFoundError


def get_current_location() -> dict[str, Any]:
    """获取当前生效的默认地理位置及其坐标与匹配精度。"""
    loc = get_default_location()
    lng, lat, level, matched_prov, matched_city = loader.lookup(
        loc["province"], loc["city"], loc["district"]
    )
    return {
        "province": matched_prov,
        "city": matched_city,
        "district": loc["district"],
        "longitude": lng,
        "latitude": lat,
        "level": level,
    }


def set_location(province: str, city: str, district: str) -> dict[str, Any]:
    """更新默认地理位置。

    步骤：
    1. 通过 data_loader.lookup() 进行省市区三级匹配并获取经纬度；
    2. 原子落盘写入 config.json 并清除缓存；
    3. 联动调度器（scheduler.reschedule()）按新经纬度重新计算 36 个触发时刻；
    4. 返回更新后的位置与坐标信息。

    Raises:
        AddressNotFoundError: 地址匹配失败
    """
    # 1. 查找并校验地址
    lng, lat, level, matched_prov, matched_city = loader.lookup(
        province, city, district
    )

    # 2. 原子写入配置文件
    update_default_location(matched_prov, matched_city, district)

    # 3. 通知调度器重新按新经纬度规划触发任务
    try:
        from .scheduler import scheduler
        scheduler.reschedule()
    except Exception:
        # 如果服务尚未完全启动或调度器未就绪，安全忽略
        pass

    return {
        "province": matched_prov,
        "city": matched_city,
        "district": district,
        "longitude": lng,
        "latitude": lat,
        "level": level,
    }
