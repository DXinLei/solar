"""
真太阳时核心计算模块。
严格基于 ephem 库，利用 ephem 原生太阳视位置计算（天然包含均时差修正），
禁止重复手动叠加均时差公式。
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import ephem
from zoneinfo import ZoneInfo

# 中国标准时区（固定 UTC+8，历史夏令时由 _correct_daylight_saving 显式修正）
CN_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc

# 十二时辰定义（按真太阳时）
SHICHEN_NAMES = [
    "子时", "丑时", "寅时", "卯时", "辰时", "巳时",
    "午时", "未时", "申时", "酉时", "戌时", "亥时",
]

# 十二时辰起始真太阳时（奇数时辰从23:00开始为"子时"）
# 子时: 23:00-01:00, 丑时: 01:00-03:00, ..., 亥时: 21:00-23:00


def _is_daylight_saving(bj_dt: datetime) -> bool:
    """判断给定北京时间是否在中国夏令时时段内（1986-1991年）。

    规则：
    - 1986年：5月4日 ~ 9月14日
    - 1987-1991年：每年4月第2个周日02:00 ~ 9月第2个周日02:00
    """
    year = bj_dt.year
    if year < 1986 or year > 1991:
        return False

    if year == 1986:
        start = datetime(1986, 5, 4, tzinfo=CN_TZ)
        end = datetime(1986, 9, 14, tzinfo=CN_TZ)
    else:
        # 4月第2个周日
        start = _nth_weekday_of_month(year, 4, 6, 2)
        # 9月第2个周日
        end = _nth_weekday_of_month(year, 9, 6, 2)
        start = start.replace(hour=2, tzinfo=CN_TZ)
        end = end.replace(hour=2, tzinfo=CN_TZ)

    return start <= bj_dt < end


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> datetime:
    """获取某年某月第 n 个星期几的日期。

    Args:
        year: 年份
        month: 月份
        weekday: 星期几（0=周一, 6=周日）
        n: 第几个
    """
    first_day = datetime(year, month, 1)
    # 计算第一个目标星期几的偏移
    days_until = (weekday - first_day.weekday()) % 7
    day = 1 + days_until + (n - 1) * 7
    return datetime(year, month, day)


def _correct_daylight_saving(bj_dt: datetime) -> tuple[datetime, bool]:
    """夏令时修正：夏令时时段内的输入时间先减1小时还原为标准北京时间。

    Returns:
        (修正后的北京时间, 是否命中夏令时)
    """
    if _is_daylight_saving(bj_dt):
        return bj_dt - timedelta(hours=1), True
    return bj_dt, False


# 十六罗盘方位角基准（0°为真北，顺时针）
_COMPASS_POINTS_16 = [
    ("正北", 0.0),
    ("东北偏北", 22.5),
    ("东北", 45.0),
    ("东北偏东", 67.5),
    ("正东", 90.0),
    ("东南偏东", 112.5),
    ("东南", 135.0),
    ("东南偏南", 157.5),
    ("正南", 180.0),
    ("西南偏南", 202.5),
    ("西南", 225.0),
    ("西南偏西", 247.5),
    ("正西", 270.0),
    ("西北偏西", 292.5),
    ("西北", 315.0),
    ("西北偏北", 337.5),
]


def _degree_to_direction(deg: float) -> str:
    """将 [0, 360) 角度映射到十六方位文字描述。"""
    idx = int(((deg + 11.25) % 360) / 22.5)
    return _COMPASS_POINTS_16[idx][0]


def _calculate_solar_all(
    lng: float, lat: float, utc_dt: datetime
) -> tuple[float, dict]:
    """基于 ephem 计算真太阳时以及太阳地平视位置（方位角、高度角）。

    Args:
        lng: 当地经度
        lat: 当地纬度
        utc_dt: UTC时间

    Returns:
        (真太阳时小时数[0.0-24.0), 太阳空间方位信息字典)
    """
    obs = ephem.Observer()
    obs.lon = str(lng)
    obs.lat = str(lat)
    obs.elevation = 0  # 海拔默认设为0
    obs.date = utc_dt

    # 通过 ephem.Sun() 计算太阳视位置，天然包含均时差修正
    sun = ephem.Sun(obs)

    # 1. 计算真太阳时角
    sidereal = float(obs.sidereal_time())  # 视恒星时（弧度）
    sun_ra = float(sun.ra)  # 太阳赤经（弧度）
    hour_angle = (sidereal - sun_ra) % (2 * ephem.pi)
    solar_hours = (hour_angle * 12 / ephem.pi + 12) % 24

    # 2. 地平坐标计算（方位角 Azimuth 与 高度角 Altitude）
    azimuth_deg = round(math.degrees(float(sun.az)), 2)
    altitude_deg = round(math.degrees(float(sun.alt)), 2)
    shadow_azimuth_deg = round((azimuth_deg + 180.0) % 360.0, 2)
    is_visible = altitude_deg > 0
    direction = _degree_to_direction(azimuth_deg)
    shadow_direction = _degree_to_direction(shadow_azimuth_deg)

    if is_visible:
        guide = (
            f"当前太阳位于【{direction}】({azimuth_deg}°)，仰角 {altitude_deg}°。"
            f"面向太阳时，真北位于左侧偏后 {round(azimuth_deg, 1)}°；"
            f"垂直物体日影严格指向【{shadow_direction}】({shadow_azimuth_deg}°)。"
        )
    else:
        guide = (
            f"当前太阳位于地平线以下（仰角 {altitude_deg}°，夜间不可见）。"
            f"当前理论天体方位为【{direction}】({azimuth_deg}°)。"
        )

    solar_pos = {
        "azimuth": azimuth_deg,
        "altitude": altitude_deg,
        "shadow_azimuth": shadow_azimuth_deg,
        "direction": direction,
        "shadow_direction": shadow_direction,
        "is_visible": is_visible,
        "orientation_guide": guide,
    }

    return solar_hours, solar_pos


def _true_solar_time(
    lng: float, lat: float, utc_dt: datetime
) -> tuple[float, datetime]:
    """向后兼容：计算真太阳时。"""
    hours, _ = _calculate_solar_all(lng, lat, utc_dt)
    return hours, utc_dt


def _hours_to_hms(hours: float) -> str:
    """将小时数转换为 HH:MM:SS 格式"""
    h = int(hours)
    m = int((hours - h) * 60)
    s = int((hours - h - m / 60) * 3600)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _hms_to_float(hms: str) -> float:
    """将 HH:MM:SS 转换为小时数（浮点）"""
    parts = hms.split(":")
    return int(parts[0]) + int(parts[1]) / 60 + int(parts[2]) / 3600


def _get_shichen(solar_hours: float) -> tuple[str, Optional[str]]:
    """根据真太阳时确定十二时辰和子时类型。

    倪派规则：
    - 真太阳时 23:00 ~ 24:00 (23:00:00 ~ 23:59:59)：晚子时
    - 真太阳时 00:00 ~ 01:00 (00:00:00 ~ 00:59:59)：早子时
    - 其余时辰：zi_shi_type 为 None

    Returns:
        (时辰名称, 子时类型或None)
    """
    if 23 <= solar_hours < 24:
        return "子时", "晚子时"
    elif 0 <= solar_hours < 1:
        return "子时", "早子时"
    else:
        idx = int((solar_hours + 1) / 2)  # 丑时从1开始
        return SHICHEN_NAMES[idx], None


class SolarCalculator:
    """真太阳时计算器"""

    def reverse_calculate(
        self,
        lng: float,
        lat: float,
        target_solar_hms: str,
        anchor_bj_dt: Optional[datetime] = None,
    ) -> datetime:
        """逆向推算：给定目标真太阳时，反算出对应的北京时间。

        原理：真太阳时 = 北京时间 + (经度-120)/15 + 均时差
        - 先扣经度修正（固定值）做粗定位
        - 再逐次逼近均时差（变化值），error 双向自动补偿

        Args:
            lng: 当地经度
            lat: 当地纬度
            target_solar_hms: 目标真太阳时 "HH:MM:SS"
            anchor_bj_dt: 锚定日期（默认当天），确定计算在哪一天

        Returns:
            北京时间 datetime（tzinfo=CN_TZ），精确到 < 1 秒

        Raises:
            ValueError: 迭代超过最大次数未收敛
        """
        target_h = _hms_to_float(target_solar_hms)

        # 锚定日期
        if anchor_bj_dt is None:
            anchor_bj_dt = datetime.now(CN_TZ)
        elif anchor_bj_dt.tzinfo is None:
            anchor_bj_dt = anchor_bj_dt.replace(tzinfo=CN_TZ)

        # 第1步：经度修正（确定值），做粗定位
        lng_offset = (lng - 120) / 15  # 小时，东经为正
        approx_h = target_h - lng_offset  # 粗猜的北京小时数

        # 构建初始猜测（用锚定日期）
        guess = anchor_bj_dt.replace(
            hour=int(approx_h) % 24,
            minute=int((approx_h % 1) * 60),
            second=0,
            microsecond=0,
        )

        # 如果粗猜落在锚定日期的前一天，往后推一天
        # 如果粗猜落在锚定日期的后一天，往前推一天
        # 通过比较 guess 和 anchor_bj_dt 的日期差来判断
        # 实际上我们想让 guess 的日期与 anchor_bj_dt 的日期对齐
        # 但目标真太阳时可能跨午夜（如子时 23:00），所以允许日期偏移

        max_iter = 10
        for i in range(max_iter):
            result = self.calculate(lng, lat, guess.strftime("%Y-%m-%d %H:%M:%S"))
            current_h = _hms_to_float(result["true_solar_time"])

            error = target_h - current_h  # 正数：目标更大 → 需推迟北京时间

            if abs(error) < 0.0003:  # < 1秒
                break

            guess += timedelta(hours=error)

        else:
            raise ValueError(
                f"逆向计算不收敛: lng={lng}, lat={lat}, "
                f"target={target_solar_hms}, "
                f"last_error={error:.4f}h"
            )

        return guess

    def calculate(
        self,
        lng: float,
        lat: float,
        bj_time_str: Optional[str] = None,
    ) -> dict:
        """计算真太阳时及相关信息。

        Args:
            lng: 当地经度（GCJ-02坐标系）
            lat: 当地纬度（GCJ-02坐标系）
            bj_time_str: 北京时间字符串 YYYY-MM-DD HH:MM:SS，None则使用当前时间

        Returns:
            包含真太阳时、时辰、排盘日期等信息的字典
        """
        # 解析输入时间
        if bj_time_str:
            bj_dt = datetime.strptime(bj_time_str, "%Y-%m-%d %H:%M:%S")
            bj_dt = bj_dt.replace(tzinfo=CN_TZ)
        else:
            bj_dt = datetime.now(CN_TZ)

        # 步骤1：夏令时修正（必须在转UTC之前完成）
        standard_bj_dt, is_dst = _correct_daylight_saving(bj_dt)

        # 步骤2：北京时间转UTC（ephem只接受UTC时间）
        utc_dt = standard_bj_dt.astimezone(UTC)

        # 步骤3：计算真太阳时与太阳地平视位置（方位角/高度角/影子朝向）
        solar_hours, solar_pos = _calculate_solar_all(lng, lat, utc_dt)

        # 步骤4：确定时辰和子时类型
        shichen, zi_type = _get_shichen(solar_hours)

        # 步骤5：计算排盘用最终日期（真太阳时刻所在的那一天）
        true_solar_str = _hours_to_hms(solar_hours)
        th, tm, ts = map(int, true_solar_str.split(":"))
        solar_sec = th * 3600 + tm * 60 + ts
        bj_sec = standard_bj_dt.hour * 3600 + standard_bj_dt.minute * 60 + standard_bj_dt.second
        delta_sec = (solar_sec - bj_sec + 12 * 3600) % (24 * 3600) - 12 * 3600
        solar_dt = standard_bj_dt + timedelta(seconds=delta_sec)
        pan_date = solar_dt.strftime("%Y-%m-%d")

        return {
            "is_daylight_saving": is_dst,
            "standard_bj_time": standard_bj_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "longitude": lng,
            "latitude": lat,
            "true_solar_time": true_solar_str,
            "solar_shichen": shichen,
            "zi_shi_type": zi_type,
            "final_pan_date": pan_date,
            "solar_position": solar_pos,
        }


# 全局计算器实例
calculator = SolarCalculator()
