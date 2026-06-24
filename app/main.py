"""FastAPI 入口：路由定义与异常处理。"""

from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse

from .config import default_location
from .data_loader import loader, AddressNotFoundError
from .solar_calculator import calculator
from .schemas import SolarTimeResponse, SolarTimeInput


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时加载行政区划数据到内存"""
    loader.load()
    yield


app = FastAPI(
    title="倪派紫微斗数真太阳时 API",
    description="基于 ephem 天文计算的真太阳时查询服务，支持十二时辰与晚子时判定",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(AddressNotFoundError)
async def address_not_found_handler(request, exc: AddressNotFoundError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/solar-time", response_model=SolarTimeResponse)
async def solar_time(
    province: str | None = Query(
        default=None,
        description="省份名称，不传则使用 config.json 中的默认值",
    ),
    city: str | None = Query(
        default=None,
        description="城市名称，不传则使用 config.json 中的默认值",
    ),
    district: str | None = Query(
        default=None,
        description="区县名称，不传则使用 config.json 中的默认值",
    ),
    bj_time: str | None = Query(
        default=None,
        description="北京时间 YYYY-MM-DD HH:MM:SS，不传则使用当前时间",
    ),
) -> SolarTimeResponse:
    """查询指定地点的真太阳时信息。

    省/市/区均可不传，未传时使用 config.json 中 default_location 的配置值；
    bj_time 不传则使用服务器当前北京时间。

    返回真太阳时、十二时辰、子时类型（晚子时/早子时）、排盘用最终日期。
    """
    # 校验：地理参数必须全部同时传入，或全部使用配置文件默认值
    geo_params = {"province": province, "city": city, "district": district}
    provided_count = sum(1 for v in geo_params.values() if v is not None)
    if provided_count not in (0, 3):
        missing = [k for k, v in geo_params.items() if v is None]
        raise HTTPException(
            status_code=400,
            detail=f"地理参数必须全部同时传入或全部省略使用默认值，当前缺少参数: {', '.join(missing)}",
        )

    # 省/市/区参数未传时使用配置文件默认值
    actual_province = province if province else default_location["province"]
    actual_city = city if city else default_location["city"]
    actual_district = district if district else default_location["district"]

    # 校验时间格式
    if bj_time is not None:
        try:
            datetime.strptime(bj_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"时间格式错误: {bj_time}，应为 YYYY-MM-DD HH:MM:SS",
            )

    # 地址匹配 → 经纬度
    try:
        lng, lat, level, matched_province, matched_city = loader.lookup(
            actual_province, actual_city, actual_district
        )
    except AddressNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"地址匹配失败: {actual_province} {actual_city} {actual_district}，请检查省市区名称是否正确",
        )

    # 真太阳时计算
    result = calculator.calculate(lng, lat, bj_time)

    # 获取实际使用的北京时间
    actual_bj_time = bj_time if bj_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return SolarTimeResponse(
        input=SolarTimeInput(
            province=matched_province,
            city=matched_city,
            district=actual_district,
            bj_time=actual_bj_time,
        ),
        is_daylight_saving=result["is_daylight_saving"],
        standard_bj_time=result["standard_bj_time"],
        longitude=result["longitude"],
        latitude=result["latitude"],
        true_solar_time=result["true_solar_time"],
        solar_shichen=result["solar_shichen"],
        zi_shi_type=result["zi_shi_type"],
        final_pan_date=result["final_pan_date"],
    )
