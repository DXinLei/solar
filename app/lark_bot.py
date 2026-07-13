"""
飞书机器人模块：WS 事件监听 + 指令处理 + 消息发送。

基于 lark-oapi 官方 SDK 实现：
- lark.ws.Client  管理 WebSocket 长连接，接收消息事件
- lark.Client  通过 REST API 发送消息
"""

import json
import logging
import re
from typing import Optional

from lark_oapi import Client, LogLevel
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import (
    P2ImMessageReceiveV1,
)
from lark_oapi.api.im.v1.model.create_message_request import CreateMessageRequest
from lark_oapi.api.im.v1.model.create_message_request_body import (
    CreateMessageRequestBody,
)

from .config import get_default_location, get_lark_config, update_default_location
from .data_loader import loader, AddressNotFoundError
from .solar_calculator import calculator

logger = logging.getLogger("lark_bot")

# 指令正则：/set 省,市,区（支持中英文逗号）
_SET_PATTERN = re.compile(
    r"^/set\s+(\S+?)\s*[,，]\s*(\S+?)\s*[,，]\s*(\S+)$",
    re.IGNORECASE,
)

# 可用指令列表（/help 的数据源）
_COMMANDS = {
    "/set": "设置默认位置，格式: /set 省,市,区",
    "/get": "查询当前真太阳时",
    "/help": "显示所有可用指令",
}


def _parse_set_command(text: str) -> tuple[str, str, str] | None:
    """解析 /set 指令，返回 (省, 市, 区) 或 None（格式不匹配）。"""
    m = _SET_PATTERN.match(text.strip())
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()


def _extract_command(text: str) -> str | None:
    """从消息文本中提取命令前缀（如 /set, /get, /help），不区分大小写。"""
    text = text.strip()
    for cmd in _COMMANDS:
        if text.lower().startswith(cmd):
            return cmd
    return None


def _build_text_content(text: str) -> str:
    """构建飞书 text 消息的 content JSON 字符串。"""
    return json.dumps({"text": text}, ensure_ascii=False)


class LarkBot:
    """飞书机器人：WS 连接 + 消息处理 + 消息发送。"""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        remind_user_open_id: str = "",
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._remind_user_open_id = remind_user_open_id

        # REST 客户端（用于发送消息，必须通过 builder 构建才能初始化 im 等子服务）
        self._rest_client = (
            Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .build()
        )

        # WS 客户端
        self._event_handler: Optional[EventDispatcherHandler] = None
        self._ws_client: Optional[lark.ws.Client] = None  # type: ignore[name-defined]

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self) -> None:
        """启动 WS 长连接（阻塞当前线程，应在后台线程中调用）。"""
        import asyncio

        import lark_oapi as lark

        # lark_oapi.ws.client 模块在导入时缓存了主线程的事件循环；
        # 在后台线程中需要覆盖为新线程的事件循环
        import lark_oapi.ws.client as _ws_mod

        _new_loop = asyncio.new_event_loop()
        _ws_mod.loop = _new_loop
        asyncio.set_event_loop(_new_loop)

        # 构建事件处理器：只注册 im.message.receive_v1
        self._event_handler = (
            EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_receive_message)
            .build()
        )

        self._ws_client = lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=self._event_handler,
            log_level=LogLevel.INFO,
        )

        logger.info("飞书 WS 客户端启动中...")
        self._ws_client.start()

    def stop(self) -> None:
        """关闭 WS 连接（由 lifespan shutdown 调用）。"""
        # lark-oapi 的 ws.Client 暂未暴露显式 stop 方法；
        # 服务进程退出时连接自然断开，此处预留。
        logger.info("飞书 WS 客户端已停止")

    # ── 事件处理 ──────────────────────────────────────────────

    def _on_receive_message(self, event: P2ImMessageReceiveV1) -> None:
        """接收飞书消息事件的回调入口。"""
        if event.event is None or event.event.message is None:
            return

        msg = event.event.message
        sender = event.event.sender

        # 提取文本内容
        text = self._extract_text(msg.content)
        if not text:
            return

        # 获取发送者的 open_id（用于回复和记录提醒目标）
        open_id = sender.sender_id.open_id if sender and sender.sender_id else ""

        logger.info(f"收到消息: open_id={open_id}, text={text[:100]}")

        # 路由指令
        text_stripped = text.strip()
        cmd = _extract_command(text_stripped)

        if cmd == "/set":
            self._handle_set_command(open_id, text_stripped)
        elif cmd == "/get":
            self._handle_get_command(open_id)
        elif cmd == "/help":
            self._handle_help_command(open_id)
        else:
            # 未知斜杠命令时回复提示
            if text_stripped.startswith("/"):
                self._send_text(
                    open_id,
                    f"未知指令: {text_stripped.split()[0]}\n输入 /help 查看所有可用指令。",
                )

    @staticmethod
    def _extract_text(content: str) -> str:
        """从飞书消息 content JSON 中提取纯文本。"""
        try:
            parsed = json.loads(content)
            return parsed.get("text", "")
        except (json.JSONDecodeError, TypeError):
            return ""

    # ── SET 指令处理 ──────────────────────────────────────────

    def _handle_set_command(self, open_id: str, text: str) -> None:
        """处理 SET 省,市,区 指令。"""
        parts = _parse_set_command(text)
        if not parts:
            self._send_text(
                open_id,
                "❌ 格式错误，请使用: /set 省,市,区\n示例: /set 四川,成都,双流区",
            )
            return

        province, city, district = parts

        # 复用 data_loader.lookup() 校验地址合法性
        try:
            lng, lat, level, matched_province, matched_city = loader.lookup(
                province, city, district
            )
        except AddressNotFoundError as e:
            self._send_text(
                open_id,
                f"❌ 地址匹配失败: {e}\n请检查省市区名称是否正确，例如: /set 四川,成都,双流区",
            )
            return

        # 原子写入 config.json
        try:
            update_default_location(matched_province, matched_city, district)
        except OSError as e:
            logger.error(f"写入 config.json 失败: {e}")
            self._send_text(open_id, f"❌ 配置文件写入失败: {e}")
            return

        # 回复成功
        level_label = {"province": "省级", "city": "市级", "district": "区级"}.get(
            level, level
        )
        self._send_text(
            open_id,
            f"✅ 默认位置已更新\n"
            f"📍 {matched_province} {matched_city} {district}\n"
            f"📌 匹配精度: {level_label}\n"
            f"🌐 经纬度: {lng:.5f}, {lat:.5f}",
        )

        logger.info(
            f"SET 指令完成: {province},{city},{district} → "
            f"{matched_province} {matched_city} {district} (level={level})"
        )

    # ── /get 指令处理 ──────────────────────────────────────────

    def _handle_get_command(self, open_id: str) -> None:
        """处理 /get 指令：查询当前真太阳时。"""
        try:
            # 1. 读取默认位置
            loc = get_default_location()

            # 2. 匹配坐标
            lng, lat, level, matched_province, matched_city = loader.lookup(
                loc["province"], loc["city"], loc["district"]
            )

            # 3. 计算真太阳时（不传 bj_time = 当前时间）
            result = calculator.calculate(lng, lat)

            # 4. 构建响应消息
            level_label = {"province": "省级", "city": "市级", "district": "区级"}.get(
                level, level
            )
            zi_label = f" ({result['zi_shi_type']})" if result.get("zi_shi_type") else ""

            lines = [
                f"📍 {matched_province} {matched_city} {loc['district']}",
                f"📌 匹配精度: {level_label}",
                f"🌐 经纬度: {lng:.5f}, {lat:.5f}",
                "",
                f"🌞 真太阳时: {result['true_solar_time']}",
                f"🕐 时辰: {result['solar_shichen']}{zi_label}",
                f"📅 日期: {result['final_pan_date']}",
                "",
                f"⏰ 标准北京时间: {result['standard_bj_time'].split()[1]}",
            ]
            if result["is_daylight_saving"]:
                lines.append("💡 当前时段曾实行夏令时，已自动修正")

            self._send_text(open_id, "\n".join(lines))

            logger.info(
                f"/get 指令完成: {matched_province} {matched_city} {loc['district']} | "
                f"真太阳时={result['true_solar_time']} | 时辰={result['solar_shichen']}"
            )

        except AddressNotFoundError as e:
            self._send_text(
                open_id,
                f"❌ 地址匹配失败: {e}\n"
                f"请先使用 /set 命令设置正确的默认位置。",
            )
        except Exception as e:
            logger.exception(f"/get 指令异常: {e}")
            self._send_text(
                open_id,
                "❌ 查询失败，请稍后重试。",
            )

    # ── /help 指令处理 ─────────────────────────────────────────

    def _handle_help_command(self, open_id: str) -> None:
        """处理 /help 指令：列出所有可用指令。"""
        lines = [
            "🤖 真太阳时机器人 — 可用指令",
            "",
        ]
        for cmd, desc in _COMMANDS.items():
            lines.append(f"  {cmd}")
            lines.append(f"    {desc}")
            lines.append("")

        lines.append("💡 提示：指令不区分大小写，如 /SET 等同于 /set。")
        lines.append("🌐 坐标数据基于高德地图 GCJ-02 坐标系。")

        self._send_text(open_id, "\n".join(lines))

    # ── 消息发送 ──────────────────────────────────────────────

    def _send_text(self, open_id: str, text: str) -> None:
        """发送文本消息到指定用户（open_id）。"""
        if not open_id:
            logger.warning("无法发送消息: open_id 为空")
            return

        try:
            body = (
                CreateMessageRequestBody.builder()
                .receive_id(open_id)
                .msg_type("text")
                .content(_build_text_content(text))
                .build()
            )
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("open_id")
                .request_body(body)
                .build()
            )
            response = self._rest_client.im.v1.message.create(request)
            if response.code != 0:
                logger.error(f"发送消息失败: code={response.code}, msg={response.msg}")
        except Exception as e:
            logger.exception(f"发送消息异常: {e}")

    def send_reminder(self, open_id: str, text: str) -> None:
        """发送定时提醒消息（对外暴露，供 scheduler.py 调用）。"""
        self._send_text(open_id, text)


# 模块级全局实例（由 main.py 的 lifespan 初始化）
bot: Optional[LarkBot] = None
