"""
通知抽象层：多渠道消息分发器。

将消息提醒（子午流注养生通知）与具体推送通道彻底解耦。
支持独立启停飞书通知、通用 Webhook 推送，或在无通知渠道时保持静默。
"""

import json
import logging
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional, Any

from .config import get_lark_config, get_webhook_config

logger = logging.getLogger("notifier")


class BaseNotifier(ABC):
    """通知渠道抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """渠道标识名"""
        pass

    @abstractmethod
    def send(self, title: str, text: str, data: Optional[dict[str, Any]] = None) -> bool:
        """发送消息

        Args:
            title: 消息标题
            text: 文本正文（可含格式化文本）
            data: 结构化元数据（供外部系统消费）

        Returns:
            bool: 发送是否成功
        """
        pass


class LarkNotifier(BaseNotifier):
    """飞书应用通知器（纯 REST API 发送，无需 WebSocket 长连接）"""

    def __init__(self, app_id: str, app_secret: str, remind_user_open_id: str) -> None:
        from lark_oapi import Client
        self._open_id = remind_user_open_id
        self._app_id = app_id
        self._client = (
            Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .build()
        )

    @property
    def name(self) -> str:
        return "lark"

    def send(self, title: str, text: str, data: Optional[dict[str, Any]] = None) -> bool:
        if not self._open_id:
            logger.warning("飞书通知未发送: remind_user_open_id 为空")
            return False

        try:
            from lark_oapi.api.im.v1.model.create_message_request import CreateMessageRequest
            from lark_oapi.api.im.v1.model.create_message_request_body import CreateMessageRequestBody

            # 飞书文本消息格式
            content_json = json.dumps({"text": text}, ensure_ascii=False)

            body = (
                CreateMessageRequestBody.builder()
                .receive_id(self._open_id)
                .msg_type("text")
                .content(content_json)
                .build()
            )
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("open_id")
                .request_body(body)
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if response.code == 0:
                logger.info(f"飞书通知发送成功: open_id={self._open_id}")
                return True
            else:
                logger.error(f"飞书通知发送失败: code={response.code}, msg={response.msg}")
                return False
        except Exception as e:
            logger.exception(f"飞书通知异常: {e}")
            return False


class WebhookNotifier(BaseNotifier):
    """通用 HTTP/HTTPS Webhook 推送通知器"""

    def __init__(self, url: str) -> None:
        self._url = url

    @property
    def name(self) -> str:
        return "webhook"

    def send(self, title: str, text: str, data: Optional[dict[str, Any]] = None) -> bool:
        if not self._url:
            return False

        payload = {
            "title": title,
            "text": text,
            "data": data or {},
        }
        req_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=req_data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                status = response.getcode()
                if 200 <= status < 300:
                    logger.info(f"Webhook 推送成功: url={self._url}")
                    return True
                else:
                    logger.warning(f"Webhook 推送返回非200: {status}")
                    return False
        except Exception as e:
            logger.error(f"Webhook 推送异常: {e}")
            return False


class NotificationManager:
    """通知管理器：集中管理与分发通知"""

    def __init__(self) -> None:
        self._notifiers: list[BaseNotifier] = []

    def register(self, notifier: BaseNotifier) -> None:
        self._notifiers.append(notifier)
        logger.info(f"已注册通知渠道: {notifier.name}")

    def clear(self) -> None:
        self._notifiers.clear()

    @property
    def has_channels(self) -> bool:
        return len(self._notifiers) > 0

    def get_channel_names(self) -> list[str]:
        return [n.name for n in self._notifiers]

    def send(self, title: str, text: str, data: Optional[dict[str, Any]] = None) -> None:
        """向所有已启用的通道分发通知。无通道时静默记录 debug。"""
        if not self._notifiers:
            logger.debug(f"无可用通知渠道，跳过通知: title={title}")
            return

        for notifier in self._notifiers:
            try:
                notifier.send(title, text, data)
            except Exception as e:
                logger.error(f"渠道 [{notifier.name}] 发送通知异常: {e}")


# 全局单例管理器
notification_manager = NotificationManager()


def init_notifiers() -> None:
    """根据最新配置初始化所有通知渠道。"""
    notification_manager.clear()

    # 1. 飞书渠道
    lark_cfg = get_lark_config()
    if lark_cfg.get("enabled") and lark_cfg.get("app_id") and lark_cfg.get("app_secret"):
        if lark_cfg.get("remind_user_open_id"):
            lark_notifier = LarkNotifier(
                app_id=lark_cfg["app_id"],
                app_secret=lark_cfg["app_secret"],
                remind_user_open_id=lark_cfg["remind_user_open_id"],
            )
            notification_manager.register(lark_notifier)
        else:
            logger.warning("飞书配置已启用，但 remind_user_open_id 为空，未注册飞书通知渠道")
    else:
        logger.info("飞书通知未启用（lark.enabled=false 或凭证缺失）")

    # 2. Webhook 渠道
    webhook_cfg = get_webhook_config()
    if webhook_cfg.get("enabled") and webhook_cfg.get("url"):
        webhook_notifier = WebhookNotifier(url=webhook_cfg["url"])
        notification_manager.register(webhook_notifier)
    else:
        logger.debug("Webhook 通知未启用")
