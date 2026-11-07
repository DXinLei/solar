"""FastAPI 入口：路由定义、异常处理、飞书机器人 + 定时调度器生命周期管理。"""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import default_location, get_default_location, get_lark_config, get_webhook_config
from .data_loader import loader, AddressNotFoundError
from .location_service import get_current_location, set_location
from .notifier import init_notifiers, notification_manager
from .health_guide import health_guide
from .solar_calculator import calculator
from .schemas import (
    SolarTimeResponse,
    SolarTimeInput,
    SolarPositionInfo,
    SolarPositionResponse,
    LocationResponse,
    LocationUpdateRequest,
    LocationInfo,
    HealthGuideItem,
    HealthGuideCurrentResponse,
    SystemStatusResponse,
    NotifierChannelStatus,
)

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("main")

_lark_bot_running: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时：加载区划数据 + 初始化通知器 + (可选)启动飞书机器人 + 启动定时调度器。"""
    global _lark_bot_running

    # 1. 加载行政区划数据
    loader.load()

    # 2. 初始化通知渠道分发器（飞书 REST / Webhook）
    init_notifiers()

    # 3. 启动飞书机器人 WS 长连接（完全受 lark.enabled 开关控制）
    lark_cfg = get_lark_config()
    if lark_cfg.get("enabled") and lark_cfg.get("app_id") and lark_cfg.get("app_secret"):
        from .lark_bot import LarkBot
        import app.lark_bot as lb

        lark_bot = LarkBot(
            app_id=lark_cfg["app_id"],
            app_secret=lark_cfg["app_secret"],
            remind_user_open_id=lark_cfg.get("remind_user_open_id", ""),
        )
        lb.bot = lark_bot

        # WS 客户端在独立线程中启动
        t = threading.Thread(target=lark_bot.start, daemon=True)
        t.start()
        _lark_bot_running = True
        logger.info("飞书 WS 长连接机器人已在后台线程启动")
    else:
        _lark_bot_running = False
        logger.info("飞书机器人已禁用（lark.enabled=false 或凭据未配置），跳过长连接启动")

    # 4. 启动定时辰提醒调度器
    from .scheduler import scheduler
    scheduler.start()

    yield

    # 关闭：停止调度器
    scheduler.stop()
    _lark_bot_running = False
    logger.info("服务已正常关闭")


app = FastAPI(
    title="倪派紫微斗数真太阳时 API",
    description="基于 ephem 天文计算的真太阳时与子午流注养生服务，支持独立 REST API 与可选飞书通知集成",
    version="1.1.0",
    lifespan=lifespan,
)


@app.exception_handler(AddressNotFoundError)
async def address_not_found_handler(request, exc: AddressNotFoundError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ── 真太阳时接口 ──────────────────────────────────────────────

@app.get("/api/solar-time", response_model=SolarTimeResponse, tags=["真太阳时"])
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

    # 省/市/区参数未传时使用配置文件默认值（热读，修改后即时生效）
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
        solar_position=SolarPositionInfo(**result["solar_position"]),
    )


@app.get("/api/solar-position", response_model=SolarPositionResponse, tags=["真太阳时与定位"])
async def solar_position(
    province: str | None = Query(
        default=None,
        description="省份名称，不传则使用默认配置",
    ),
    city: str | None = Query(
        default=None,
        description="城市名称，不传则使用默认配置",
    ),
    district: str | None = Query(
        default=None,
        description="区县名称，不传则使用默认配置",
    ),
    bj_time: str | None = Query(
        default=None,
        description="北京时间 YYYY-MM-DD HH:MM:SS，不传则使用当前时间",
    ),
) -> SolarPositionResponse:
    """查询太阳天体视位置（方位角、仰角、垂直日影反向角度及定向操作指引）。

    专供安卓 App、网页罗盘与实景定向使用，精度达 0.01°，免疫室内钢筋电磁干扰。
    """
    geo_params = {"province": province, "city": city, "district": district}
    provided_count = sum(1 for v in geo_params.values() if v is not None)
    if provided_count not in (0, 3):
        missing = [k for k, v in geo_params.items() if v is None]
        raise HTTPException(
            status_code=400,
            detail=f"地理参数必须全部同时传入或全部省略，当前缺少参数: {', '.join(missing)}",
        )

    actual_loc = get_default_location()
    actual_province = province if province else actual_loc["province"]
    actual_city = city if city else actual_loc["city"]
    actual_district = district if district else actual_loc["district"]

    if bj_time is not None:
        try:
            datetime.strptime(bj_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"时间格式错误: {bj_time}，应为 YYYY-MM-DD HH:MM:SS",
            )

    try:
        lng, lat, level, matched_province, matched_city = loader.lookup(
            actual_province, actual_city, actual_district
        )
    except AddressNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"地址匹配失败: {actual_province} {actual_city} {actual_district}",
        )

    result = calculator.calculate(lng, lat, bj_time)
    actual_bj_time = bj_time if bj_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return SolarPositionResponse(
        input=SolarTimeInput(
            province=matched_province,
            city=matched_city,
            district=actual_district,
            bj_time=actual_bj_time,
        ),
        standard_bj_time=result["standard_bj_time"],
        true_solar_time=result["true_solar_time"],
        solar_shichen=result["solar_shichen"],
        solar_position=SolarPositionInfo(**result["solar_position"]),
    )


# ── 地理位置管理接口 ──────────────────────────────────────────

@app.get("/api/location", response_model=LocationResponse, tags=["位置管理"])
async def get_location() -> LocationResponse:
    """获取当前服务配置的默认地理位置及坐标。"""
    try:
        info = get_current_location()
        return LocationResponse(
            message="ok",
            data=LocationInfo(
                province=info["province"],
                city=info["city"],
                district=info["district"],
                longitude=info["longitude"],
                latitude=info["latitude"],
                level=info["level"],
            ),
        )
    except AddressNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/location", response_model=LocationResponse, tags=["位置管理"])
async def update_location(body: LocationUpdateRequest) -> LocationResponse:
    """更新默认地理位置。

    校验地址有效性，原子写入 config.json，并立即同步重算重载 36 个触发时刻任务。
    """
    try:
        info = set_location(body.province, body.city, body.district)
        return LocationResponse(
            message="默认地理位置已更新，调度器任务已同步刷新",
            data=LocationInfo(
                province=info["province"],
                city=info["city"],
                district=info["district"],
                longitude=info["longitude"],
                latitude=info["latitude"],
                level=info["level"],
            ),
        )
    except AddressNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"地址匹配失败: {e}，请检查省市区名称是否正确",
        )


# ── 养生指南接口 ──────────────────────────────────────────────

@app.get("/api/health-guide", tags=["养生指南"])
async def get_health_guide(
    shichen: Optional[str] = Query(
        default=None,
        description="时辰名称（如'子时'、'午时'）。不传则返回全部十二时辰养生数据。",
    ),
):
    """查询指定时辰或全部十二时辰的《黄帝内经》养生指南与经络穴位。"""
    if shichen:
        guide = health_guide.get_guide(shichen)
        if not guide:
            raise HTTPException(
                status_code=404,
                detail=f"未找到时辰: {shichen}，有效时辰为: {', '.join(health_guide.get_shichen_names())}",
            )
        return {"shichen": shichen, "guide": guide}
    return {"guides": health_guide.get_all_guides()}


@app.get("/api/health-guide/current", response_model=HealthGuideCurrentResponse, tags=["养生指南"])
async def get_current_health_guide() -> HealthGuideCurrentResponse:
    """根据当前默认位置与实时真太阳时，查询当前正处于的时辰及养生指导。"""
    loc_info = get_current_location()
    result = calculator.calculate(loc_info["longitude"], loc_info["latitude"])
    sc = result["solar_shichen"]
    guide_dict = health_guide.get_guide(sc)
    if not guide_dict:
        raise HTTPException(status_code=500, detail=f"养生数据缺失: {sc}")

    next_sc = health_guide.get_next_shichen(sc)

    return HealthGuideCurrentResponse(
        province=loc_info["province"],
        city=loc_info["city"],
        district=loc_info["district"],
        true_solar_time=result["true_solar_time"],
        standard_bj_time=result["standard_bj_time"],
        solar_shichen=sc,
        zi_shi_type=result.get("zi_shi_type"),
        guide=HealthGuideItem(**guide_dict),
        next_shichen=next_sc,
    )


@app.post("/api/health-guide/notify-test", tags=["养生指南"])
async def test_notify():
    """手动触发一次当前时辰的养生提醒测试通知，校验已启用的通知渠道（飞书/Webhook）。"""
    loc_info = get_current_location()
    result = calculator.calculate(loc_info["longitude"], loc_info["latitude"])
    sc = result["solar_shichen"]

    text = health_guide.build_message(
        shichen=sc,
        phase="start",
        true_solar_time=result["true_solar_time"],
        standard_bj_time=result["standard_bj_time"],
        final_pan_date=result["final_pan_date"],
        zi_type=result.get("zi_shi_type"),
        province=loc_info["province"],
        city=loc_info["city"],
        district=loc_info["district"],
        advance_minutes=15,
    )
    if not text:
        text = f"测试通知：当前为 {sc}，真太阳时 {result['true_solar_time']}"

    notification_manager.send(
        title=f"【测试提醒】子午流注·{sc}",
        text=text,
        data={
            "test": True,
            "shichen": sc,
            "true_solar_time": result["true_solar_time"],
        },
    )

    channels = notification_manager.get_channel_names()
    return {
        "message": "测试提醒已触发",
        "active_channels": channels,
        "channel_count": len(channels),
    }


# ── 系统运行状态接口 ──────────────────────────────────────────

@app.get("/api/status", response_model=SystemStatusResponse, tags=["系统状态"])
async def get_system_status() -> SystemStatusResponse:
    """获取服务端整体运行状态（当前位置、通知渠道状态、调度任务数量等）。"""
    from .scheduler import scheduler

    loc_info = get_current_location()
    lark_cfg = get_lark_config()
    webhook_cfg = get_webhook_config()

    channels = [
        NotifierChannelStatus(
            name="lark",
            enabled=lark_cfg.get("enabled", False),
            details=f"open_id={lark_cfg.get('remind_user_open_id', '')[:6]}***" if lark_cfg.get("remind_user_open_id") else "未配置open_id",
        ),
        NotifierChannelStatus(
            name="webhook",
            enabled=webhook_cfg.get("enabled", False),
            details=webhook_cfg.get("url") or "未配置URL",
        ),
    ]

    return SystemStatusResponse(
        version="1.1.0",
        current_location=LocationInfo(**loc_info),
        notifiers=channels,
        lark_bot_running=_lark_bot_running,
        scheduler_running=scheduler.is_running(),
        scheduled_jobs_count=scheduler.get_job_count(),
    )


# ── 客户端实时调试日志接收接口 ──────────────────────────────────

@app.post("/api/debug-log", tags=["系统状态"])
async def receive_debug_log(req: Request) -> dict:
    """接收来自安卓真机客户端的实时调试跟踪日志与崩溃堆栈。"""
    try:
        body = await req.json()
        level = body.get("level", "INFO")
        tag = body.get("tag", "Android")
        msg = body.get("message", "")
        logger.info(f"📱 [{level}][{tag}] {msg}")
    except Exception:
        raw = await req.body()
        logger.info(f"📱 [RAW] {raw.decode('utf-8', errors='ignore')}")
    return {"status": "ok"}

