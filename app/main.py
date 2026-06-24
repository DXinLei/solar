"""FastAPI 入口：路由定义、异常处理、飞书机器人 + 定时调度器生命周期管理。"""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse

from .config import default_location, get_default_location, get_lark_config
from .data_loader import loader, AddressNotFoundError
from .solar_calculator import calculator
from .schemas import SolarTimeResponse, SolarTimeInput

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时：加载数据 + 启动飞书 WS + 启动定时调度器。"""
    # 加载行政区划数据
    loader.load()

    # 启动飞书机器人 WS（异步后台线程）
    from .lark_bot import LarkBot, bot as lark_bot_module
    from .config import get_lark_config

    lark_cfg = get_lark_config()
    if lark_cfg["app_id"] and lark_cfg["app_secret"]:
        lark_bot = LarkBot(
            app_id=lark_cfg["app_id"],
            app_secret=lark_cfg["app_secret"],
            remind_user_open_id=lark_cfg.get("remind_user_open_id", ""),
        )
        # 将实例设到模块全局，供 scheduler 使用
        import app.lark_bot as lb
        lb.bot = lark_bot

        # WS 客户端在独立线程中启动（start() 内部创建自己的事件循环）
        t = threading.Thread(target=lark_bot.start, daemon=True)
        t.start()
        logger.info("飞书 WS 客户端已在后台线程启动")
    else:
        logger.warning("未配置飞书 app_id/app_secret，飞书功能不可用")

    # 启动定时辰提醒调度器
    from .scheduler import scheduler
    scheduler.start()

    yield

    # 关闭：停止调度器
    scheduler.stop()
    logger.info("服务已关闭")


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

    # 省/市/区参数未传时使用配置文件默认值（热读，飞书 SET 修改后即时生效）
    actual_loc = get_default_location()
    actual_province = province if province else actual_loc["province"]
    actual_city = city if city else actual_loc["city"]
    actual_district = district if district else actual_loc["district"]

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
