"""飞书机器人命令单元测试"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.lark_bot import LarkBot, _parse_set_command, _extract_command
from app.data_loader import loader


def test_bot_commands():
    loader.load()

    # 1. 命令解析测试
    assert _extract_command("/set 四川,成都,双流区") == "/set"
    assert _extract_command("/GET") == "/get"
    assert _extract_command("/Help") == "/help"
    assert _extract_command("/unknown") is None

    # 2. 参数解析测试
    parts = _parse_set_command("/set 四川,成都,双流区")
    assert parts == ("四川", "成都", "双流区")

    parts_cn = _parse_set_command("/set 广东，广州，天河区")
    assert parts_cn == ("广东", "广州", "天河区")

    assert _parse_set_command("/set 缺少参数") is None

    # 3. 模拟机器人实例（不启动 WS，只测内部消息处理与回复捕获）
    bot = LarkBot(app_id="dummy", app_secret="dummy", remind_user_open_id="ou_test")

    sent_replies = []
    bot._send_text = lambda open_id, text: sent_replies.append({"open_id": open_id, "text": text})

    # 测试 /help
    bot._handle_help_command("user_1")
    assert len(sent_replies) == 1
    assert "可用指令" in sent_replies[0]["text"]

    # 测试 /get
    bot._handle_get_command("user_1")
    assert len(sent_replies) == 2
    assert "真太阳时" in sent_replies[1]["text"]

    # 测试 /set 合法地址
    bot._handle_set_command("user_1", "/set 四川,成都,双流区")
    assert len(sent_replies) == 3
    assert "默认位置已更新" in sent_replies[2]["text"]

    # 测试 /set 非法地址
    bot._handle_set_command("user_1", "/set 火星,基地,一区")
    assert len(sent_replies) == 4
    assert "地址匹配失败" in sent_replies[3]["text"]

    print("飞书机器人命令测试全部通过！")


if __name__ == "__main__":
    test_bot_commands()
