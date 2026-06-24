"""
养生指南消息构建模块。

加载 data/health_guide.json，按十二时辰三阶段构建差异化的飞书消息。

三阶段消息差异化策略：
- 开始（start）:   时辰开启 + 理论依据 + 核心该做什么
- 中段（middle）:  简易养护方法 + 穴位按摩
- 结束前（before_end）: 禁忌提醒 + 下一时辰预告
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("health_guide")

# 数据文件路径
_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "health_guide.json"

# 十二时辰顺序（用于查找下一个时辰）
_SHICHEN_ORDER = [
    "子时", "丑时", "寅时", "卯时", "辰时", "巳时",
    "午时", "未时", "申时", "酉时", "戌时", "亥时",
]


class HealthGuide:
    """养生指南加载与消息构建。"""

    def __init__(self) -> None:
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        """加载 health_guide.json。"""
        if not _DATA_PATH.exists():
            logger.warning(f"养生数据文件不存在: {_DATA_PATH}")
            return
        try:
            with open(_DATA_PATH, encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info(f"已加载 {len(self._data)} 个时辰的养生数据")
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"加载养生数据失败: {e}")

    def get_shichen_names(self) -> list[str]:
        """获取所有已加载的时辰名称。"""
        return list(self._data.keys())

    def get_next_shichen(self, current: str) -> Optional[str]:
        """获取下一个时辰名称。"""
        idx = _SHICHEN_ORDER.index(current) if current in _SHICHEN_ORDER else -1
        if idx == -1:
            return None
        return _SHICHEN_ORDER[(idx + 1) % 12]

    def build_message(
        self,
        shichen: str,
        phase: str,
        true_solar_time: str,
        standard_bj_time: str,
        final_pan_date: str,
        zi_type: Optional[str],
        province: str,
        city: str,
        district: str,
        advance_minutes: int = 15,
    ) -> Optional[str]:
        """构建三阶段养身提醒消息。

        Args:
            shichen: 时辰名称，如 "巳时"
            phase: 阶段，"start" | "middle" | "before_end"
            true_solar_time: 当前真太阳时
            standard_bj_time: 标准北京时间
            final_pan_date: 排盘日期
            zi_type: 子时类型
            province/city/district: 地理位置
            advance_minutes: 结束前提前分钟数

        Returns:
            格式化的消息文本，或 None（数据未加载）
        """
        info = self._data.get(shichen)
        if info is None:
            logger.warning(f"未找到养生数据: {shichen}")
            return None

        zi_label = f" ({zi_type})" if zi_type else ""

        # 阶段标签
        phase_labels = {
            "start": "⏰ 时辰开始",
            "middle": "🔄 时辰中段",
            "before_end": f"⏳ 结束前 {advance_minutes} 分钟",
        }
        phase_label = phase_labels.get(phase, phase)

        # ── 构建消息主体 ──
        lines: list[str] = []

        # 头部
        lines.append(f"🕐 {shichen}{zi_label} — {info['meridian']}")
        lines.append(f"📋 {phase_label}")
        lines.append("")

        # 地点信息（精简一行）
        lines.append(f"📍 {province} {city} {district} | 🌞 {true_solar_time}")

        # 关键词
        lines.append(f"💡 {info['keyword']}")
        lines.append("")

        # ── 按阶段差异化 ──
        if phase == "start":
            lines.append(f"📖 {info['theory']}")
            lines.append("")
            lines.append("✅ 宜做：")
            for d in info["dos"][:3]:  # 取前 3 条最重要的
                lines.append(f"  • {d}")
            if info["acupoints"]:
                lines.append("")
                lines.append(f"👐 按揉穴位：{'、'.join(info['acupoints'])}")

        elif phase == "middle":
            lines.append("🌿 简易养护：")
            lines.append(f"  {info['simple_care']}")
            if info["acupoints"]:
                lines.append("")
                lines.append(f"👐 穴位按摩：{'、'.join(info['acupoints'])}")

        elif phase == "before_end":
            lines.append("❌ 禁忌提醒：")
            for d in info["donts"][:2]:  # 取前 2 条
                lines.append(f"  • {d}")
            lines.append("")

            # 预告下一个时辰
            next_sc = self.get_next_shichen(shichen)
            if next_sc and next_sc in self._data:
                next_info = self._data[next_sc]
                lines.append("")
                lines.append(f"⏭️ 下个时辰预告：")
                lines.append(f"   {next_sc}（{next_info['time_range']}）")
                lines.append(f"   {next_info['meridian']}")
                lines.append(f"   💡 {next_info['keyword']}")

        lines.append("")
        lines.append(f"📅 {final_pan_date} | ⏰ {standard_bj_time.split()[1]}")

        return "\n".join(lines)


# 全局单例
health_guide = HealthGuide()
