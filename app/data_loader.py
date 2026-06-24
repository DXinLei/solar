"""
数据加载模块：读取行政区划数据并实现地址→经纬度匹配。
数据来源：AreaCity-JsSpider-StatsGov 仓库的 CSV 数据。

坐标系说明：
- 所有坐标数据来自高德地图，为 GCJ-02（火星坐标系）
- GCJ-02 对真太阳时计算误差小于24秒，命理场景可直接使用，无需坐标转换
"""

import csv as csv_mod
from pathlib import Path
from typing import Optional

import pandas as pd

# ok_geo.csv 的 polygon 字段（WKT 边界数据）可能超大，提高 CSV field limit
# Windows 上 sys.maxsize 会溢出，使用 2^31-1 安全上限
csv_mod.field_size_limit(2_147_483_647)

# 项目根目录（app/ 的父目录）
ROOT = Path(__file__).resolve().parent.parent

# CSV 数据目录
DATA_DIR = ROOT / "data"
LEVEL3_PATH = DATA_DIR / "ok_data_level3.csv"   # 省市区三级名录
LEVEL4_PATH = DATA_DIR / "ok_data_level4.csv"   # 省市区乡镇四级名录（预留）
GEO_PATH = DATA_DIR / "ok_geo.csv"               # 省市区三级中心点坐标+边界


class AddressNotFoundError(Exception):
    """地址匹配失败异常"""
    pass


class AreaDataLoader:
    """行政区划数据加载器，启动时一次性加载到内存。

    数据关联：
    - ok_data_level3.csv 提供省/市/区名录（deep: 0=省, 1=市, 2=区）
    - ok_geo.csv 通过 id 字段关联，提供中心点经纬度
    - geo 字段格式 "经度 纬度"（空格分隔），拆分后经度在前、纬度在后
    """

    def __init__(self) -> None:
        self._level3: pd.DataFrame | None = None
        self._level4: pd.DataFrame | None = None
        self._geo: pd.DataFrame | None = None
        # 层级索引：{id: {"name": str, "pid": str, "lng": float|None, "lat": float|None}}
        self._provinces: dict[str, dict] = {}
        self._cities: dict[str, dict] = {}
        self._districts: dict[str, dict] = {}

    # ── 加载入口 ──────────────────────────────────────────────

    def load(self) -> None:
        """启动时一次性加载所有数据到内存"""
        self._load_level3()
        self._load_geo()
        self._build_hierarchy()

    def load_level4(self) -> None:
        """预留：加载四级行政区划名录，暂不接入主业务逻辑。

        四级名录无免费坐标数据，后续扩展地址联动时再使用。
        """
        if not LEVEL4_PATH.exists():
            raise FileNotFoundError(f"四级数据文件不存在: {LEVEL4_PATH}")
        self._level4 = pd.read_csv(
            LEVEL4_PATH, encoding="utf-8-sig", dtype={"id": str, "pid": str}
        )

    # ── CSV 读取 ──────────────────────────────────────────────

    def _load_level3(self) -> None:
        """读取 ok_data_level3.csv（省市区三级名录）。

        utf-8-sig 编码避免首列 BOM 乱码，id/pid 以字符串读取保留前导零。
        """
        if not LEVEL3_PATH.exists():
            raise FileNotFoundError(f"数据文件不存在: {LEVEL3_PATH}")
        self._level3 = pd.read_csv(
            LEVEL3_PATH, encoding="utf-8-sig", dtype={"id": str, "pid": str}
        )

    def _load_geo(self) -> None:
        """读取 ok_geo.csv，拆分 geo 字段为浮点型 lng/lat。

        geo 原始格式："经度 纬度"（空格分隔），"EMPTY" 表示无坐标。
        经度在前、纬度在后，顺序绝对不能颠倒。
        """
        if not GEO_PATH.exists():
            raise FileNotFoundError(f"坐标数据文件不存在: {GEO_PATH}")
        self._geo = pd.read_csv(
            GEO_PATH,
            encoding="utf-8-sig",
            dtype={"id": str, "pid": str},
        )
        # 拆分 "经度 纬度" → lng, lat
        geo_split = self._geo["geo"].str.split(" ", expand=True)
        self._geo["lng"] = pd.to_numeric(geo_split[0], errors="coerce")
        self._geo["lat"] = pd.to_numeric(geo_split[1], errors="coerce")

    # ── 层级索引构建 ──────────────────────────────────────────

    def _build_hierarchy(self) -> None:
        """以 ok_data_level3 名录为骨架，通过 id 关联 ok_geo 坐标，
        构建省-市-区三层索引，存入内存字典供后续查询。
        """
        if self._level3 is None:
            return

        # 将 geo 数据转为 {id: (lng, lat)} 快速查找表
        geo_map: dict[str, tuple[float, float]] = {}
        if self._geo is not None:
            for _, row in self._geo.iterrows():
                rid = str(row["id"])
                lng = row.get("lng")
                lat = row.get("lat")
                if pd.notna(lng) and pd.notna(lat):
                    geo_map[rid] = (float(lng), float(lat))

        # 省级（deep=0）
        for _, row in self._level3[self._level3["deep"] == 0].iterrows():
            pid = str(row["id"])
            self._provinces[pid] = {
                "name": row["name"],
                "lng": geo_map[pid][0] if pid in geo_map else None,
                "lat": geo_map[pid][1] if pid in geo_map else None,
            }

        # 市级（deep=1）
        for _, row in self._level3[self._level3["deep"] == 1].iterrows():
            cid = str(row["id"])
            pid = str(row["pid"])
            self._cities[cid] = {
                "name": row["name"],
                "pid": pid,
                "lng": geo_map[cid][0] if cid in geo_map else None,
                "lat": geo_map[cid][1] if cid in geo_map else None,
            }

        # 区级（deep=2）
        for _, row in self._level3[self._level3["deep"] == 2].iterrows():
            did = str(row["id"])
            pid = str(row["pid"])
            self._districts[did] = {
                "name": row["name"],
                "pid": pid,
                "lng": geo_map[did][0] if did in geo_map else None,
                "lat": geo_map[did][1] if did in geo_map else None,
            }

    # ── 名称匹配 ──────────────────────────────────────────────

    @staticmethod
    def _name_match(input_name: str, stored_name: str) -> bool:
        """判断两个地名是否匹配：互为子串。

        例如：'四川' 匹配 '四川'、'四川省'；'双流' 匹配 '双流区'。
        注意：此方法在跨级匹配时可能误命中，仅在 pid 已限定的子集中使用。
        """
        return input_name in stored_name or stored_name in input_name

    # ── 地址查找与降级 ────────────────────────────────────────

    def lookup(
        self, province: str, city: str, district: str
    ) -> tuple[float, float, str, str, str]:
        """输入省/市/区名称，返回 (经度, 纬度, 匹配层级, 省名, 市名)。

        降级策略（坐标精度逐级回退）：
        1. 精准匹配区级中心点 → level="district"
        2. 区级匹配失败或无坐标 → 降级匹配市级中心点 → level="city"
        3. 市级匹配失败或无坐标 → 降级匹配省级中心点 → level="province"
        4. 省级也无坐标 → 抛出 AddressNotFoundError
        """
        # 步骤1：匹配省份
        matched_province_id: Optional[str] = None
        matched_province_name: Optional[str] = None
        for pid, pinfo in self._provinces.items():
            if self._name_match(province, pinfo["name"]):
                matched_province_id = pid
                matched_province_name = pinfo["name"]
                break
        if matched_province_id is None:
            raise AddressNotFoundError(f"未找到省份: {province}")

        # 步骤2：匹配城市（限定在已匹配省份下）
        matched_city_id: Optional[str] = None
        matched_city_name: Optional[str] = None
        for cid, cinfo in self._cities.items():
            if cinfo["pid"] == matched_province_id and self._name_match(city, cinfo["name"]):
                matched_city_id = cid
                matched_city_name = cinfo["name"]
                break

        # 步骤3：匹配区级（限定在已匹配城市下）
        matched_district_id: Optional[str] = None
        if matched_city_id:
            for did, dinfo in self._districts.items():
                if dinfo["pid"] == matched_city_id and self._name_match(district, dinfo["name"]):
                    matched_district_id = did
                    break

        # 步骤4：按优先级取坐标 — 区 > 市 > 省
        lng: Optional[float] = None
        lat: Optional[float] = None
        level = "province"

        # 优先区级坐标
        if matched_district_id and matched_district_id in self._districts:
            dinfo = self._districts[matched_district_id]
            if dinfo["lng"] is not None and dinfo["lat"] is not None:
                lng = dinfo["lng"]
                lat = dinfo["lat"]
                level = "district"

        # 降级市级坐标
        if lng is None and matched_city_id and matched_city_id in self._cities:
            cinfo = self._cities[matched_city_id]
            if cinfo["lng"] is not None and cinfo["lat"] is not None:
                lng = cinfo["lng"]
                lat = cinfo["lat"]
                level = "city"

        # 降级省级坐标
        if lng is None and matched_province_id in self._provinces:
            pinfo = self._provinces[matched_province_id]
            if pinfo["lng"] is not None and pinfo["lat"] is not None:
                lng = pinfo["lng"]
                lat = pinfo["lat"]
                level = "province"

        if lng is None or lat is None:
            raise AddressNotFoundError(
                f"地址匹配成功但无坐标数据: {matched_province_name} "
                f"{matched_city_name or '?'} {district}，"
                f"请确认 ok_geo.csv 文件中是否包含该区域坐标"
            )

        return lng, lat, level, matched_province_name or province, matched_city_name or city


# 全局单例，启动时加载
loader = AreaDataLoader()
