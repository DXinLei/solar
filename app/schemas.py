"""Pydantic v2 数据模型：请求/响应结构。"""

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
