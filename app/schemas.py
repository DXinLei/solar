"""Pydantic v2 数据模型：请求/响应结构。"""

from typing import Optional, Any
from pydantic import BaseModel, Field


class SolarTimeRequest(BaseModel):
    """真太阳时查询请求"""
    province: str | None = Field(default=None, description="省份名称，不传使用 config.json 默认值")
    city: str | None = Field(default=None, description="城市名称，不传使用 config.json 默认值")
    district: str | None = Field(default=None, description="区县名称，不传使用 config.json 默认值")
    bj_time: str | None = Field(
        default=None,
        description="北京时间 YYYY-MM-DD HH:MM:SS，不传则使用当前时间",
    )


class SolarTimeInput(BaseModel):
    """响应中的输入信息"""
    province: str
    city: str
    district: str
    bj_time: str


class SolarPositionInfo(BaseModel):
    """太阳空间视位置（地平坐标系与影子定向参数）"""
    azimuth: float = Field(description="太阳方位角（0°~360°，真北为0°，顺时针：90°东/180°南/270°西）")
    altitude: float = Field(description="太阳高度角/仰角（-90°~90°，>0表示在地平线上白天可见）")
    shadow_azimuth: float = Field(description="垂直物体日影朝向（0°~360°，太阳反向，用于量角器对齐）")
    direction: str = Field(description="太阳所在十六方位描述（如：东南偏南、正南）")
    shadow_direction: str = Field(description="影子所处十六方位描述（如：西北偏北）")
    is_visible: bool = Field(description="太阳是否升起在天空中")
    orientation_guide: str = Field(description="实操定向指引提示语")


class SolarTimeResponse(BaseModel):
    """真太阳时查询响应"""
    input: SolarTimeInput
    is_daylight_saving: bool = Field(description="是否命中夏令时且已修正")
    standard_bj_time: str = Field(description="夏令时修正后的标准北京时间")
    longitude: float = Field(description="当地经度（GCJ-02坐标系）")
    latitude: float = Field(description="当地纬度（GCJ-02坐标系）")
    true_solar_time: str = Field(description="真太阳时，HH:MM:SS格式")
    solar_shichen: str = Field(description="十二时辰名称")
    zi_shi_type: str | None = Field(default=None, description="子时类型：晚子时/早子时，非子时返回null")
    final_pan_date: str = Field(description="排盘用最终日期，YYYY-MM-DD")
    solar_position: SolarPositionInfo = Field(description="太阳视位置及定向参数")


class SolarPositionResponse(BaseModel):
    """太阳空间方位与定向专有响应"""
    input: SolarTimeInput
    standard_bj_time: str = Field(description="标准北京时间")
    true_solar_time: str = Field(description="当地真太阳时")
    solar_shichen: str = Field(description="对应时辰")
    solar_position: SolarPositionInfo = Field(description="太阳视位置及定向参数")


# ── 地理位置管理模型 ──────────────────────────────────────────

class LocationInfo(BaseModel):
    """地理位置及坐标信息"""
    province: str = Field(description="省份规范名称")
    city: str = Field(description="城市规范名称")
    district: str = Field(description="区县名称")
    longitude: float = Field(description="中心点经度（GCJ-02坐标系）")
    latitude: float = Field(description="中心点纬度（GCJ-02坐标系）")
    level: str = Field(description="匹配精度：district（区级）/ city（市级）/ province（省级）")


class LocationUpdateRequest(BaseModel):
    """更新默认地理位置请求"""
    province: str = Field(..., description="省份名称，支持模糊名称如'四川'或'四川省'")
    city: str = Field(..., description="城市名称，支持模糊名称如'成都'或'成都市'")
    district: str = Field(..., description="区县名称，支持模糊名称如'双流'或'双流区'")


class LocationResponse(BaseModel):
    """位置查询/更新响应"""
    message: str = Field(default="ok", description="操作结果消息")
    data: LocationInfo


# ── 养生指南模型 ──────────────────────────────────────────────

class HealthGuideItem(BaseModel):
    """单个时辰养生详情"""
    time_range: str = Field(description="真太阳时区间")
    meridian: str = Field(description="对应经络全称")
    meridian_short: str = Field(description="对应经络简称")
    keyword: str = Field(description="时辰养生核心口诀")
    theory: str = Field(description="黄帝内经理论依据")
    dos: list[str] = Field(description="核心宜做事项")
    donts: list[str] = Field(description="核心禁忌事项")
    simple_care: str = Field(description="简易养护方法")
    acupoints: list[str] = Field(description="推荐按揉穴位")


class HealthGuideCurrentResponse(BaseModel):
    """当前实时养生指南响应"""
    province: str
    city: str
    district: str
    true_solar_time: str
    standard_bj_time: str
    solar_shichen: str
    zi_shi_type: str | None = None
    guide: HealthGuideItem
    next_shichen: Optional[str] = None


# ── 系统运行状态模型 ──────────────────────────────────────────

class NotifierChannelStatus(BaseModel):
    """通知渠道状态"""
    name: str
    enabled: bool
    details: Optional[str] = None


class SystemStatusResponse(BaseModel):
    """系统运行状态"""
    version: str
    current_location: LocationInfo
    notifiers: list[NotifierChannelStatus]
    lark_bot_running: bool
    scheduler_running: bool
    scheduled_jobs_count: int
