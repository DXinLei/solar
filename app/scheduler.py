"""
定时辰提醒模块：基于逆向计算的精确触发调度器。

核心逻辑：
- 用 reverse_calculate() 将目标真太阳时精确反算为北京时间
- 用 APScheduler DateTrigger 在精确时刻触发，误差 < 1 秒
- 每个触发点触发后自动注册下一次（次日同一真太阳时）

12 时辰 × 3 阶段 = 36 个触发点：
- start:     时辰开始时刻
- middle:    时辰中点时刻
- before_end: 时辰结束前 N 分钟（默认 15）
"""

import logging
from datetime import datetime, timedelta, date as date_mod
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from zoneinfo import ZoneInfo

from .config import get_default_location, get_reminder_config
from .data_loader import loader
from .solar_calculator import calculator

logger = logging.getLogger("scheduler")

CN_TZ = ZoneInfo("Asia/Shanghai")

# 十二时辰真太阳时区间
# 子时跨天用 [23, 25) 表示，内部统一归一化
SHICHEN_RANGES: list[tuple[str, float, float]] = [
    ("子时", 23, 25),  # 23:00 ~ 01:00（跨天）
    ("丑时", 1, 3),
    ("寅时", 3, 5),
    ("卯时", 5, 7),
    ("辰时", 7, 9),
    ("巳时", 9, 11),
    ("午时", 11, 13),
    ("未时", 13, 15),
    ("申时", 15, 17),
    ("酉时", 17, 19),
    ("戌时", 19, 21),
    ("亥时", 21, 23),
]


def _normalize_hour(h: float) -> float:
    """归一化小时数到 [0, 24)。"""
    return h % 24


def _get_trigger_points(advance_minutes: int) -> list[dict]:
    """生成所有触发点的真太阳时。

    Returns:
        [{ "shichen": str, "solar_hour": float, "phase": str, "label": str }, ...]
    """
    points: list[dict] = []
    for name, start_h, end_h in SHICHEN_RANGES:
        duration = end_h - start_h  # 子时=2h, 其他=2h
        midpoint = (start_h + end_h) / 2
        before_end = end_h - advance_minutes / 60

        phase_info = [
            ("start", start_h, "开始"),
            ("middle", midpoint, "中段"),
            ("before_end", before_end, f"结束前{advance_minutes}分钟"),
        ]

        for phase_key, solar_hour, phase_label in phase_info:
            points.append({
                "shichen": name,
                "solar_hour": _normalize_hour(solar_hour),
                "phase": phase_key,
                "label": f"{name}{phase_label}",
            })

    return points


class ShichenScheduler:
    """定时辰提醒调度器（精确触发版）。"""

    def __init__(self) -> None:
        self._scheduler: Optional[BackgroundScheduler] = None
        self._advance_minutes: int = 15

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self) -> None:
        """启动调度器：注册所有即将到来的触发点。"""
        cfg = get_reminder_config()
        if not cfg["enabled"]:
            logger.info("定时提醒已禁用，调度器未启动")
            return

        self._advance_minutes = cfg.get("advance_minutes", 15)

        self._scheduler = BackgroundScheduler(timezone=CN_TZ)
        self._schedule_all_upcoming()
        self._scheduler.start()

        # 统计已注册数量
        jobs = self._scheduler.get_jobs()
        logger.info(f"时辰提醒调度器已启动，已注册 {len(jobs)} 个触发任务")

    def stop(self) -> None:
        """停止调度器。"""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("时辰提醒调度器已停止")

    # ── 调度逻辑 ──────────────────────────────────────────────

    def _schedule_all_upcoming(self) -> None:
        """加载当前地理位置，为所有未来触发点注册一次性 DateTrigger。"""
        try:
            loc = get_default_location()
            lng, lat, _level, province, city = loader.lookup(
                loc["province"], loc["city"], loc["district"]
            )
        except Exception:
            logger.exception("地址匹配失败，无法启动提醒调度器")
            return

        # 获取所有触发点
        points = _get_trigger_points(self._advance_minutes)

        # 获取当前真太阳时（用于判断哪些触发点还在今天）
        now_result = calculator.calculate(lng, lat)
        current_solar_h = _hms_to_float(now_result["true_solar_time"])

        now_bj = datetime.now(CN_TZ)
        today = now_bj.date()
        tomorrow = today + timedelta(days=1)

        registered = 0
        for pt in points:
            # 尝试用今天作为锚定日期
            target_bj = self._try_schedule_for_date(
                lng, lat, pt, today, province, city, loc["district"],
            )
            if target_bj is None:
                # 今天的已过，尝试明天
                target_bj = self._try_schedule_for_date(
                    lng, lat, pt, tomorrow, province, city, loc["district"],
                )

            if target_bj is not None:
                registered += 1

        if registered == 0:
            logger.warning("没有注册任何触发点，请检查配置")

    def _try_schedule_for_date(
        self,
        lng: float,
        lat: float,
        pt: dict,
        target_date: date_mod,
        province: str,
        city: str,
        district: str,
    ) -> Optional[datetime]:
        """尝试为某个触发点在指定日期注册任务。

        如果计算出的北京时间已经过去，则跳过（返回 None）。
        """
        now_bj = datetime.now(CN_TZ)

        # 构建锚定日期时间（取该日正午，作为迭代起点）
        anchor = datetime(
            target_date.year, target_date.month, target_date.day,
            12, 0, 0, tzinfo=CN_TZ,
        )

        try:
            # 逆向计算：目标真太阳时 → 北京时间
            target_bj = calculator.reverse_calculate(
                lng, lat,
                _hours_to_hms_str(pt["solar_hour"]),
                anchor_bj_dt=anchor,
            )
        except (ValueError, Exception) as e:
            logger.warning(
                f"逆向计算失败: {pt['label']} @ {target_date}, err={e}"
            )
            return None

        # 如果目标时间已过，跳过
        if target_bj <= now_bj:
            return None

        # 注册一次性任务
        job_id = f"{pt['shichen']}_{pt['phase']}_{target_date.isoformat()}"
        self._scheduler.add_job(
            self._on_trigger,
            DateTrigger(run_date=target_bj),
            id=job_id,
            name=f"{pt['label']} @ {target_date}",
            args=[
                lng, lat,
                pt["shichen"], pt["solar_hour"], pt["phase"],
                province, city, district,
            ],
        )

        logger.info(
            f"已注册: {pt['label']:12s} | "
            f"真太阳时={_hours_to_hms_str(pt['solar_hour'])} | "
            f"北京时间={target_bj.strftime('%m-%d %H:%M:%S')}"
        )
        return target_bj

    # ── 触发回调 ──────────────────────────────────────────────

    def _on_trigger(
        self,
        lng: float,
        lat: float,
        shichen: str,
        solar_hour: float,
        phase: str,
        province: str,
        city: str,
        district: str,
    ) -> None:
        """触发点到达时执行：发送提醒 + 注册下一次。"""
        try:
            # 1. 发送提醒消息
            self._send_notification(
                lng, lat, shichen, solar_hour, phase,
                province, city, district,
            )

            # 2. 注册下一次触发（明天同一时刻）
            tomorrow = datetime.now(CN_TZ).date() + timedelta(days=1)
            anchor = datetime(
                tomorrow.year, tomorrow.month, tomorrow.day,
                12, 0, 0, tzinfo=CN_TZ,
            )
            next_bj = calculator.reverse_calculate(
                lng, lat,
                _hours_to_hms_str(solar_hour),
                anchor_bj_dt=anchor,
            )

            job_id = f"{shichen}_{phase}_{tomorrow.isoformat()}"
            self._scheduler.add_job(
                self._on_trigger,
                DateTrigger(run_date=next_bj),
                id=job_id,
                name=f"{shichen} {phase} @ {tomorrow}",
                args=[
                    lng, lat,
                    shichen, solar_hour, phase,
                    province, city, district,
                ],
            )

            logger.info(
                f"已注册下一次: {shichen} {phase} @ "
                f"{next_bj.strftime('%m-%d %H:%M:%S')}"
            )

        except Exception:
            logger.exception(f"触发回调异常: {shichen} {phase}")

    # ── 消息发送 ──────────────────────────────────────────────

    def _send_notification(
        self,
        lng: float,
        lat: float,
        shichen: str,
        solar_hour: float,
        phase: str,
        province: str,
        city: str,
        district: str,
    ) -> None:
        """发送养生提醒消息到飞书（基于 health_guide.json 内容）。"""
        from .lark_bot import bot
        from .config import get_lark_config
        from .health_guide import health_guide

        if bot is None:
            logger.warning("飞书机器人未初始化，跳过提醒")
            return

        lark_cfg = get_lark_config()
        open_id = lark_cfg.get("remind_user_open_id", "")
        if not open_id:
            logger.warning("未配置 remind_user_open_id，跳过提醒")
            return

        # 重新计算当前真太阳时（此时正是触发点）
        result = calculator.calculate(lng, lat)

        # 使用养生指南构建消息
        text = health_guide.build_message(
            shichen=shichen,
            phase=phase,
            true_solar_time=result["true_solar_time"],
            standard_bj_time=result["standard_bj_time"],
            final_pan_date=result["final_pan_date"],
            zi_type=result.get("zi_shi_type"),
            province=province,
            city=city,
            district=district,
            advance_minutes=self._advance_minutes,
        )

        if text is None:
            # 养生数据未加载时，降级为简单消息
            zi_label = f" ({result.get('zi_shi_type')})" if result.get('zi_shi_type') else ""
            phase_labels = {"start": "开始", "middle": "中段", "before_end": f"结束前{self._advance_minutes}分钟"}
            text = (
                f"🕐 {shichen}{zi_label} {phase_labels.get(phase, phase)}\n"
                f"📍 {province} {city} {district}\n"
                f"🌞 {result['true_solar_time']} | 📅 {result['final_pan_date']}"
            )

        bot.send_reminder(open_id, text)
        logger.info(
            f"已发送养生提醒: {shichen} {phase} | "
            f"真太阳时={result['true_solar_time']}"
        )


def _hms_to_float(hms: str) -> float:
    parts = hms.split(":")
    return int(parts[0]) + int(parts[1]) / 60 + int(parts[2]) / 3600


def _hours_to_hms_str(h: float) -> str:
    h = h % 24
    hi = int(h)
    mi = int((h - hi) * 60)
    si = int(((h - hi) * 60 - mi) * 60)
    return f"{hi:02d}:{mi:02d}:{si:02d}"


# 全局单例
scheduler = ShichenScheduler()
