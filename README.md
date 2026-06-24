# 倪派紫微斗数真太阳时 API

基于 FastAPI + ephem 的真太阳时计算服务，支持十二时辰养生与紫微斗数排盘。

## 技术栈

- **Python 3.11+** + **uv** 包管理
- **FastAPI** HTTP 接口
- **ephem (PyEphem)** 天文级太阳视位置计算
- **pandas** 行政区划数据处理
- **Pydantic v2** 数据校验

## 启动命令

```bash
# 安装依赖
uv sync

# 启动服务
uv run uvicorn app.main:app --reload
```

## API 接口

### GET /api/solar-time

查询指定地点的真太阳时信息。

**请求参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| province | string | config.json | 省份名称，不传使用配置文件默认值，支持模糊匹配 |
| city | string | config.json | 城市名称，不传使用配置文件默认值，支持模糊匹配 |
| district | string | config.json | 区县名称，不传使用配置文件默认值，支持模糊匹配 |
| bj_time | string | 当前时间 | 北京时间 YYYY-MM-DD HH:MM:SS，不传则使用当前时间 |

**示例请求：**

```bash
# 全部使用默认值（config.json 配置的省市区 + 当前时间）
curl "http://127.0.0.1:8000/api/solar-time"

# 指定时间，地区使用默认值
curl "http://127.0.0.1:8000/api/solar-time?bj_time=1994-12-16+22:30:00"

# 只改省份，市/区沿用默认值
curl "http://127.0.0.1:8000/api/solar-time?province=广东省"

# 完整指定省市区和时间
curl "http://127.0.0.1:8000/api/solar-time?province=广东省&city=深圳市&district=南山区&bj_time=2026-06-24+12:00:00"
```

**默认地区配置：**

编辑根目录 `config.json` 即可切换默认省市区，无需重启服务（每次请求实时读取）：

```json
{
  "default_location": {
    "province": "四川省",
    "city": "成都市",
    "district": "双流区"
  }
}
```

**示例响应：**

```json
{
  "input": {
    "province": "四川",
    "city": "成都",
    "district": "双流区",
    "bj_time": "2026-06-24 12:00:00"
  },
  "is_daylight_saving": false,
  "standard_bj_time": "2026-06-24 12:00:00",
  "longitude": 103.92342,
  "latitude": 30.574884,
  "true_solar_time": "10:53:17",
  "solar_shichen": "巳时",
  "zi_shi_type": null,
  "final_pan_date": "2026-06-24"
}
```

**响应字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| input | object | 实际使用的省市区和时间 |
| is_daylight_saving | bool | 是否命中1986-1991年中国夏令时，true表示已自动修正 |
| standard_bj_time | string | 夏令时修正后的标准北京时间 |
| longitude | float | 匹配到的当地经度（GCJ-02坐标系） |
| latitude | float | 匹配到的当地纬度（GCJ-02坐标系） |
| true_solar_time | string | 计算得到的真太阳时，HH:MM:SS格式 |
| solar_shichen | string | 对应十二时辰名称 |
| zi_shi_type | string\|null | 子时类型："早子时"/"晚子时"，非子时返回null |
| final_pan_date | string | 排盘用最终日期，处理晚子时日期偏移 |

## 项目结构

```
solar/
├── AreaCity-JsSpider-StatsGov/     # 开源行政区划数据（禁止修改）
│   └── src/采集到的数据/
│       ├── ok_data_level3.csv      # 省市区三级名录
│       ├── ok_data_level4.csv      # 省市区乡镇四级名录（预留）
│       └── ok_geo.csv              # 省市区中心点坐标+边界
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI 入口 + /api/solar-time 路由
│   ├── data_loader.py              # CSV数据加载 + 三级降级地址匹配
│   ├── solar_calculator.py         # ephem真太阳时 + 夏令时 + 十二时辰
│   └── schemas.py                  # Pydantic v2 请求/响应模型
├── pyproject.toml
├── .python-version
└── README.md
```

## 核心规则

### 真太阳时计算

- 基于 ephem 库原生太阳视位置计算，天然包含均时差（Equation of Time）修正
- 通过太阳时角换算为当地真太阳时，无需手动叠加均时差公式
- 输入北京时间 → 夏令时修正 → 转UTC → ephem计算 → 真太阳时

### 倪派晚子时规则

- 真太阳时 23:00~00:00：**晚子时**，排盘日期沿用前一天
- 真太阳时 00:00~01:00：**早子时**，排盘日期按当天
- 判定严格基于最终计算出的真太阳时，不用原始北京时间

### 十二时辰对照

| 时辰 | 真太阳时区间 | 时辰 | 真太阳时区间 |
|------|-------------|------|-------------|
| 子时 | 23:00-01:00 | 午时 | 11:00-13:00 |
| 丑时 | 01:00-03:00 | 未时 | 13:00-15:00 |
| 寅时 | 03:00-05:00 | 申时 | 15:00-17:00 |
| 卯时 | 05:00-07:00 | 酉时 | 17:00-19:00 |
| 辰时 | 07:00-09:00 | 戌时 | 19:00-21:00 |
| 巳时 | 09:00-11:00 | 亥时 | 21:00-23:00 |

### 中国夏令时修正（1986-1991）

- 1986年：5月4日 ~ 9月14日
- 1987-1991年：每年4月第2个周日 02:00 ~ 9月第2个周日 02:00
- 夏令时时段内的输入时间自动减1小时还原为标准北京时间

## 地址匹配与降级策略

数据源为 `ok_geo.csv`，覆盖 **34个省级**、**372个市级**、**2851个区级** 行政区划中心点坐标。

地址匹配按三级降级：

1. **区级精确匹配** → 返回区县中心点坐标
2. 区级匹配失败或无坐标 → 降级返回**市级中心点**坐标
3. 市级匹配失败或无坐标 → 降级返回**省级中心点**坐标
4. 全部失败 → 返回 400 状态码

名称支持模糊匹配，如"双流"可匹配"双流区"，"成都"可匹配"成都市"。

## 坐标系统

数据来源为高德地图 **GCJ-02（火星坐标系）**，对真太阳时计算误差小于24秒，命理场景可直接使用，无需坐标转换。
