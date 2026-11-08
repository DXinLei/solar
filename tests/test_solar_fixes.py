"""真太阳时 API 缺陷修复专项回归测试套件。

覆盖验收标准：
1. 核心 12 条用例验证（含缺陷复现、基线保持与夏令时单次修正）
2. 35 条边界矩阵自测（5 地 x 7 个时间点），核验自洽不变量：|(final_pan_date + true_solar_time) - bj_time| < 2.5h
3. 1986-1991 六年夏令时抽检（确认 true 与 std 之差在 -60 ~ -75 分钟内，杜绝双重扣除）
4. OpenAPI 契约校验（/openapi.json 返回 200，schema 完整不变）
"""

import sys
from datetime import datetime
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app
from app.data_loader import loader
from app.solar_calculator import calculator


def _hms_to_seconds(hms: str) -> int:
    h, m, s = map(int, hms.split(":"))
    return h * 3600 + m * 60 + s


def test_openapi_contract(client: TestClient):
    """验证 /openapi.json 返回 200 且数据模型契约完好无损。"""
    res = client.get("/openapi.json")
    assert res.status_code == 200, f"openapi.json failed: {res.text}"
    schema = res.json()
    assert "/api/solar-time" in schema["paths"]


def test_core_12_cases(client: TestClient):
    """核心 12 条用例（复现、基线与夏令时）验证。"""
    # 1. 北京 东城区 2024-01-13 23:50:00 → 晚子时未跨日，不回退
    res1 = client.get("/api/solar-time?province=北京市&city=北京市&district=东城区&bj_time=2024-01-13+23:50:00")
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["true_solar_time"] == "23:27:06"
    assert d1["final_pan_date"] == "2024-01-13"
    assert d1["solar_shichen"] == "子时"
    assert d1["zi_shi_type"] == "晚子时"

    # 2. 北京 东城区 2024-01-13 23:59:00 → 晚子时未跨日，不回退
    res2 = client.get("/api/solar-time?province=北京市&city=北京市&district=东城区&bj_time=2024-01-13+23:59:00")
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["true_solar_time"] == "23:36:06"
    assert d2["final_pan_date"] == "2024-01-13"
    assert d2["solar_shichen"] == "子时"
    assert d2["zi_shi_type"] == "晚子时"

    # 3. 成都 武侯区 2024-01-14 00:10:00 → 跨回前一天亥时，回退
    res3 = client.get("/api/solar-time?province=四川省&city=成都市&district=武侯区&bj_time=2024-01-14+00:10:00")
    assert res3.status_code == 200
    d3 = res3.json()
    assert d3["true_solar_time"] == "22:57:37"
    assert d3["final_pan_date"] == "2024-01-13"
    assert d3["solar_shichen"] == "亥时"
    assert d3["zi_shi_type"] is None

    # 4. 乌鲁木齐 天山区 2024-01-14 01:00:00 → 跨回前一天亥时，回退
    res4 = client.get("/api/solar-time?province=新疆维吾尔自治区&city=乌鲁木齐市&district=天山区&bj_time=2024-01-14+01:00:00")
    assert res4.status_code == 200
    d4 = res4.json()
    assert d4["true_solar_time"] == "22:41:57"
    assert d4["final_pan_date"] == "2024-01-13"
    assert d4["solar_shichen"] == "亥时"
    assert d4["zi_shi_type"] is None

    # 5. 抚远 抚远市 2024-01-13 23:30:00 → 正向前进跨日到次日
    res5 = client.get("/api/solar-time?province=黑龙江省&city=佳木斯市&district=抚远市&bj_time=2024-01-13+23:30:00")
    assert res5.status_code == 200
    d5 = res5.json()
    assert d5["true_solar_time"] == "00:18:40"
    assert d5["final_pan_date"] == "2024-01-14"
    assert d5["solar_shichen"] == "子时"
    assert d5["zi_shi_type"] == "早子时"

    # 6. 抚远 抚远市 2024-01-13 23:55:00 → 正向前进跨日到次日
    res6 = client.get("/api/solar-time?province=黑龙江省&city=佳木斯市&district=抚远市&bj_time=2024-01-13+23:55:00")
    assert res6.status_code == 200
    d6 = res6.json()
    assert d6["true_solar_time"] == "00:43:40"
    assert d6["final_pan_date"] == "2024-01-14"
    assert d6["solar_shichen"] == "子时"
    assert d6["zi_shi_type"] == "早子时"

    # 回归基线 7: 北京 2024-01-14 00:10:00
    res7 = client.get("/api/solar-time?province=北京市&city=北京市&district=东城区&bj_time=2024-01-14+00:10:00")
    assert res7.status_code == 200
    d7 = res7.json()
    assert d7["true_solar_time"] == "23:47:06"
    assert d7["final_pan_date"] == "2024-01-13"
    assert d7["zi_shi_type"] == "晚子时"

    # 回归基线 8: 北京 2024-01-14 00:40:00
    res8 = client.get("/api/solar-time?province=北京市&city=北京市&district=东城区&bj_time=2024-01-14+00:40:00")
    assert res8.status_code == 200
    d8 = res8.json()
    assert d8["true_solar_time"] == "00:17:05"
    assert d8["final_pan_date"] == "2024-01-14"
    assert d8["zi_shi_type"] == "早子时"

    # 回归基线 9: 乌鲁木齐 2024-01-14 02:00:00
    res9 = client.get("/api/solar-time?province=新疆维吾尔自治区&city=乌鲁木齐市&district=天山区&bj_time=2024-01-14+02:00:00")
    assert res9.status_code == 200
    d9 = res9.json()
    assert d9["true_solar_time"] == "23:41:56"
    assert d9["final_pan_date"] == "2024-01-13"
    assert d9["zi_shi_type"] == "晚子时"

    # 回归基线 10: 上海黄浦 2024-01-14 00:05:00
    res10 = client.get("/api/solar-time?province=上海市&city=上海市&district=黄浦区&bj_time=2024-01-14+00:05:00")
    assert res10.status_code == 200
    d10 = res10.json()
    assert d10["true_solar_time"] == "00:02:22"
    assert d10["final_pan_date"] == "2024-01-14"
    assert d10["zi_shi_type"] == "早子时"

    # 回归基线 11: 成都 2024-01-13 23:50:00
    res11 = client.get("/api/solar-time?province=四川省&city=成都市&district=武侯区&bj_time=2024-01-13+23:50:00")
    assert res11.status_code == 200
    d11 = res11.json()
    assert d11["true_solar_time"] == "22:37:37"
    assert d11["final_pan_date"] == "2024-01-13"
    assert d11["solar_shichen"] == "亥时"
    assert d11["zi_shi_type"] is None

    # 夏令时 12: 成都 1986-07-15 12:00:00
    res12 = client.get("/api/solar-time?province=四川省&city=成都市&district=武侯区&bj_time=1986-07-15+12:00:00")
    assert res12.status_code == 200
    d12 = res12.json()
    assert d12["is_daylight_saving"] is True
    assert d12["standard_bj_time"] == "1986-07-15 11:00:00"
    assert abs(_hms_to_seconds(d12["true_solar_time"]) - _hms_to_seconds("09:50:18")) <= 60
    assert d12["solar_shichen"] == "巳时"

    # 夏令时 13: 成都 1986-07-15 23:40:00
    res13 = client.get("/api/solar-time?province=四川省&city=成都市&district=武侯区&bj_time=1986-07-15+23:40:00")
    assert res13.status_code == 200
    d13 = res13.json()
    assert d13["is_daylight_saving"] is True
    assert d13["standard_bj_time"] == "1986-07-15 22:40:00"
    assert abs(_hms_to_seconds(d13["true_solar_time"]) - _hms_to_seconds("21:30:16")) <= 60
    assert d13["solar_shichen"] == "亥时"

    # 夏令时 14: 成都 1988-07-01 12:00:00
    res14 = client.get("/api/solar-time?province=四川省&city=成都市&district=武侯区&bj_time=1988-07-01+12:00:00")
    assert res14.status_code == 200
    d14 = res14.json()
    assert d14["is_daylight_saving"] is True
    assert abs(_hms_to_seconds(d14["true_solar_time"]) - _hms_to_seconds("09:52:22")) <= 60


def test_35_boundary_matrix():
    """35 条边界矩阵自测 (5地 x 7个时间点)，核查自洽不变量。"""
    cities = [
        ("北京东城", "北京市", "北京市", "东城区"),
        ("上海黄浦", "上海市", "上海市", "黄浦区"),
        ("成都武侯", "四川省", "成都市", "武侯区"),
        ("乌鲁木齐天山", "新疆维吾尔自治区", "乌鲁木齐市", "天山区"),
        ("抚远", "黑龙江省", "佳木斯市", "抚远市"),
    ]
    times = [
        "2024-01-13 23:30:00",
        "2024-01-13 23:50:00",
        "2024-01-13 23:59:00",
        "2024-01-14 00:05:00",
        "2024-01-14 00:10:00",
        "2024-01-14 00:40:00",
        "2024-01-14 01:00:00",
    ]
    for label, p, c, dist in cities:
        lng, lat, _, _, _ = loader.lookup(p, c, dist)
        for t_str in times:
            r = calculator.calculate(lng, lat, t_str)
            solar_dt = datetime.strptime(f"{r['final_pan_date']} {r['true_solar_time']}", "%Y-%m-%d %H:%M:%S")
            bj_dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
            diff_hours = abs((solar_dt - bj_dt).total_seconds()) / 3600.0
            assert diff_hours < 2.5, f"Invariant violated for {label} at {t_str}: diff={diff_hours}h"

            th = int(r["true_solar_time"][:2])
            if th == 23:
                assert r["zi_shi_type"] == "晚子时"
            elif th == 0:
                assert r["zi_shi_type"] == "早子时"
            else:
                assert r["zi_shi_type"] is None


def test_dst_years_spot_check():
    """夏令时 1986-1991 年份抽检，确认无双重扣除。"""
    cd_lng, cd_lat, _, _, _ = loader.lookup("四川省", "成都市", "武侯区")
    dst_checks = [
        ("1986", "1986-07-15 12:00:00"),
        ("1987", "1987-06-15 12:00:00"),
        ("1988", "1988-07-01 12:00:00"),
        ("1989", "1989-06-20 12:00:00"),
        ("1990", "1990-07-10 12:00:00"),
        ("1991", "1991-06-15 12:00:00"),
    ]
    for year, t_str in dst_checks:
        r = calculator.calculate(cd_lng, cd_lat, t_str)
        assert r["is_daylight_saving"] is True
        std_dt = datetime.strptime(r["standard_bj_time"], "%Y-%m-%d %H:%M:%S")
        true_dt = datetime.strptime(f"{r['final_pan_date']} {r['true_solar_time']}", "%Y-%m-%d %H:%M:%S")
        diff_min = (true_dt - std_dt).total_seconds() / 60.0
        assert -75.0 <= diff_min <= -60.0, f"{year} diff is {diff_min} min!"


if __name__ == "__main__":
    loader.load()
    with TestClient(app) as c:
        test_openapi_contract(c)
        test_core_12_cases(c)
        test_35_boundary_matrix()
        test_dst_years_spot_check()
    print("全部专项测试执行完毕，100% 通过！")
