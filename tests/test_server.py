"""服务端及解耦通知模块全面功能测试"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.main import app
from app.config import get_default_location, get_lark_config
from app.location_service import set_location, get_current_location
from app.notifier import notification_manager, BaseNotifier
from app.scheduler import scheduler


class MockNotifier(BaseNotifier):
    def __init__(self):
        self.sent_messages = []

    @property
    def name(self) -> str:
        return "mock"

    def send(self, title: str, text: str, data=None) -> bool:
        self.sent_messages.append({"title": title, "text": text, "data": data})
        return True


def test_full_workflow():
    # 使用 TestClient 触发 lifespan (执行 loader.load() 等)
    with TestClient(app) as client:
        # 确保起点为四川成都双流区
        set_location("四川省", "成都市", "双流区")

        print("\n=== 1. 测试系统状态接口 GET /api/status ===")
        res = client.get("/api/status")
        assert res.status_code == 200, res.text
        data = res.json()
        print(f"Status response: version={data['version']}, jobs={data['scheduled_jobs_count']}, lark_bot_running={data['lark_bot_running']}")
        assert data["version"] == "1.1.0"
        assert data["scheduler_running"] is True
        assert data["lark_bot_running"] is False  # lark.enabled = false
        assert data["scheduled_jobs_count"] > 0

        print("\n=== 2. 测试真太阳时查询 GET /api/solar-time ===")
        res = client.get("/api/solar-time?province=四川省&city=成都市&district=双流区&bj_time=2026-06-24+12:00:00")
        assert res.status_code == 200, res.text
        solar_data = res.json()
        print(f"Solar time: {solar_data['true_solar_time']}, shichen: {solar_data['solar_shichen']}")
        assert "true_solar_time" in solar_data
        assert solar_data["solar_shichen"] == "巳时"
        assert "solar_position" in solar_data
        pos = solar_data["solar_position"]
        print(f"Solar pos: az={pos['azimuth']}° ({pos['direction']}), alt={pos['altitude']}°, shadow={pos['shadow_azimuth']}°")
        assert 0 <= pos["azimuth"] <= 360
        assert -90 <= pos["altitude"] <= 90

        print("\n=== 2.1 测试太阳地平坐标与定向接口 GET /api/solar-position ===")
        res = client.get("/api/solar-position")
        assert res.status_code == 200, res.text
        pos_resp = res.json()
        print(f"Current solar pos: {pos_resp['solar_position']['direction']} (az={pos_resp['solar_position']['azimuth']}°)")
        print(f"Orientation guide: {pos_resp['solar_position']['orientation_guide']}")
        assert "orientation_guide" in pos_resp["solar_position"]

        print("\n=== 3. 测试获取当前位置 GET /api/location ===")
        res = client.get("/api/location")
        assert res.status_code == 200, res.text
        loc_data = res.json()["data"]
        print(f"Current location: {loc_data['province']} {loc_data['city']} {loc_data['district']} ({loc_data['level']})")
        assert "双流" in loc_data["district"]

        print("\n=== 4. 测试更新位置 POST /api/location (切换到广州天河区并恢复) ===")
        try:
            update_res = client.post(
                "/api/location",
                json={"province": "广东省", "city": "广州市", "district": "天河区"},
            )
            assert update_res.status_code == 200, update_res.text
            new_loc = update_res.json()["data"]
            print(f"Updated location: {new_loc['province']} {new_loc['city']} {new_loc['district']}")
            assert "广州" in new_loc["city"]
            assert "天河" in new_loc["district"]
            assert scheduler.get_job_count() > 0

            # 验证读取
            res = client.get("/api/location")
            assert "天河" in res.json()["data"]["district"]
        finally:
            # 恢复默认位置为四川成都双流区
            restore_res = client.post(
                "/api/location",
                json={"province": "四川省", "city": "成都市", "district": "双流区"},
            )
            assert restore_res.status_code == 200
            print("Restored location back to 四川成都双流区")

        print("\n=== 5. 测试养生指南接口 GET /api/health-guide ===")
        # 全量
        res = client.get("/api/health-guide")
        assert res.status_code == 200
        guides = res.json()["guides"]
        assert len(guides) == 12
        assert "子时" in guides
        assert "午时" in guides

        # 单个时辰
        res = client.get("/api/health-guide?shichen=午时")
        assert res.status_code == 200
        wushi = res.json()["guide"]
        assert wushi["meridian_short"] == "心经"
        print(f"午时 keyword: {wushi['keyword']}")

        # 实时当前时辰
        res = client.get("/api/health-guide/current")
        assert res.status_code == 200
        cur = res.json()
        print(f"Current health guide: {cur['solar_shichen']}, meridian: {cur['guide']['meridian']}")
        assert "solar_shichen" in cur

        print("\n=== 6. 测试通知管理器与测试触发接口 ===")
        # 注册 mock 接收器
        mock_notifier = MockNotifier()
        notification_manager.register(mock_notifier)

        res = client.post("/api/health-guide/notify-test")
        assert res.status_code == 200
        print("Notify test result:", res.json())
        assert len(mock_notifier.sent_messages) == 1
        assert "子午流注" in mock_notifier.sent_messages[0]["title"]
        print("Mock received:", mock_notifier.sent_messages[0]["title"])

        print("\n=== 所有测试均顺利通过！ ===")


if __name__ == "__main__":
    test_full_workflow()
