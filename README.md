# 倪派紫微斗数真太阳时 API

基于 **FastAPI + ephem** 的真太阳时计算服务，集成**飞书机器人**与**子午流注十二时辰养生提醒**。

## 功能特性

- 🌞 **真太阳时计算** — 基于 ephem 天文库，自动含均时差修正
- 🕐 **十二时辰判定** — 支持倪派晚子时规则（23:00-00:00 为晚子时）
- ⏰ **夏令时修正** — 自动处理 1986-1991 年中国夏令时
- 🤖 **飞书机器人** — 接收 `SET 省,市,区` 指令修改默认位置
- 🌿 **子午流注养生提醒** — 每时辰三阶段推送（开始/中段/结束前），含《黄帝内经》养生指导
- 📍 **三级地址降级** — 区→市→省自动降级匹配

## 技术栈

| 技术 | 用途 |
|------|------|
| **Python 3.11+** | 运行环境 |
| **FastAPI** | HTTP 接口 |
| **ephem (PyEphem)** | 天文级太阳视位置计算 |
| **pandas** | 行政区划数据处理 |
| **Pydantic v2** | 数据校验 |
| **lark-oapi** | 飞书官方 SDK（WebSocket 长连） |
| **APScheduler** | 精确触发定时任务 |

## 快速启动

### 方式一：本地运行

```bash
# 1. 安装依赖
pip install -e .

# 2. 准备数据文件
# 确保 data/ 目录下包含以下文件：
#   - ok_data_level3.csv
#   - ok_data_level4.csv
#   - ok_geo.csv（160MB，需手动放置）

# 3. 创建配置文件
cp config.example.json config.json
# 编辑 config.json 填入飞书 App ID / App Secret / open_id

# 4. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 方式二：Docker 部署（推荐）

```bash
# 1. 准备数据文件
# 确保 data/ok_geo.csv 已放置（160MB，不在 Git 中）

# 2. 创建配置文件
cp config.example.json config.json
# 编辑 config.json 填入飞书 App ID / App Secret / open_id

# 3. 构建并启动
docker compose up -d

# 4. 查看日志
docker compose logs -f
```

## 项目结构

```
solar/
├── Dockerfile                  # Docker 镜像构建
├── docker-compose.yml          # Docker Compose 编排
├── config.example.json         # 配置模板（脱敏）
├── .gitignore
├── pyproject.toml
├── data/
│   ├── health_guide.json       # 十二时辰养生数据库
│   ├── ok_data_level3.csv      # 省市区三级名录（Git 管理）
│   ├── ok_data_level4.csv      # 省市区乡镇四级名录（Git 管理）
│   └── ok_geo.csv              # 省市区中心点坐标（160MB，需手动放置）
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口 + 生命周期管理
│   ├── config.py               # 配置热读 + 原子写入
│   ├── data_loader.py          # CSV 数据加载 + 地址匹配
│   ├── solar_calculator.py     # 真太阳时计算 + 逆向推算
│   ├── schemas.py              # Pydantic v2 数据模型
│   ├── lark_bot.py             # 飞书机器人（WS + SET 指令）
│   ├── scheduler.py            # 精确触发调度器
│   └── health_guide.py         # 养生消息构建
└── README.md
```

## API 接口

### GET /api/solar-time

查询指定地点的真太阳时信息。

**请求参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| province | string | config.json | 省份名称，不传使用配置文件默认值。省/市/区必须**全部传入**或**全部省略** |
| city | string | config.json | 同上 |
| district | string | config.json | 同上 |
| bj_time | string | 当前时间 | 北京时间 YYYY-MM-DD HH:MM:SS |

**示例请求：**

```bash
# 全部使用默认值（config.json 配置的省市区 + 当前时间）
curl "http://127.0.0.1:8000/api/solar-time"

# 指定时间，地区使用默认值
curl "http://127.0.0.1:8000/api/solar-time?bj_time=1994-12-16+22:30:00"

# ❌ 错误：只改省份（缺少 city/district 会报 400）
# curl "http://127.0.0.1:8000/api/solar-time?province=广东省"

# ✅ 完整指定省市区和时间（必须全部传入）
curl "http://127.0.0.1:8000/api/solar-time?province=广东省&city=深圳市&district=南山区&bj_time=2026-06-24+12:00:00"
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
| longitude | float | 当地经度（GCJ-02坐标系） |
| latitude | float | 当地纬度（GCJ-02坐标系） |
| true_solar_time | string | 真太阳时 HH:MM:SS |
| solar_shichen | string | 十二时辰名称 |
| zi_shi_type | string\|null | 子时类型："早子时"/"晚子时"，非子时返回null |
| final_pan_date | string | 排盘用最终日期，处理晚子时日期偏移 |

## 飞书机器人

### SET 指令

在飞书中向机器人发送指令可修改默认地理位置：

```
SET 四川,成都,双流区
```

支持中英文逗号分隔，地址会自动模糊匹配并验证。

### 子午流注养生提醒

每时辰推送 3 次养生消息：

| 阶段 | 推送内容 |
|------|---------|
| ⏰ **时辰开始** | 内经理论 + 核心宜做事项 + 穴位推荐 |
| 🔄 **时辰中段** | 简易养护方法 + 穴位按摩 |
| ⏳ **结束前** | 禁忌提醒 + 下个时辰预告 |

## 核心规则

### 真太阳时计算

- 基于 ephem 库原生太阳视位置计算，天然包含均时差修正
- 输入北京时间 → 夏令时修正 → 转UTC → ephem计算 → 真太阳时
- 支持**逆向推算**：给定目标真太阳时，反算精确北京时间

### 倪派晚子时规则

- 真太阳时 23:00~00:00：**晚子时**，排盘日期沿用前一天
- 真太阳时 00:00~01:00：**早子时**，排盘日期按当天

### 十二时辰对照

| 时辰 | 真太阳时区间 | 经络 | 时辰 | 真太阳时区间 | 经络 |
|------|-------------|------|------|-------------|------|
| 子时 | 23:00-01:00 | 胆经 | 午时 | 11:00-13:00 | 心经 |
| 丑时 | 01:00-03:00 | 肝经 | 未时 | 13:00-15:00 | 小肠经 |
| 寅时 | 03:00-05:00 | 肺经 | 申时 | 15:00-17:00 | 膀胱经 |
| 卯时 | 05:00-07:00 | 大肠经 | 酉时 | 17:00-19:00 | 肾经 |
| 辰时 | 07:00-09:00 | 胃经 | 戌时 | 19:00-21:00 | 心包经 |
| 巳时 | 09:00-11:00 | 脾经 | 亥时 | 21:00-23:00 | 三焦经 |

### 中国夏令时修正（1986-1991）

- 1986年：5月4日 ~ 9月14日
- 1987-1991年：每年4月第2个周日 02:00 ~ 9月第2个周日 02:00

## 地址匹配与降级策略

地址匹配按三级降级：

1. **区级精确匹配** → 返回区县中心点坐标
2. 区级匹配失败或无坐标 → 降级返回**市级中心点**坐标
3. 市级匹配失败或无坐标 → 降级返回**省级中心点**坐标
4. 全部失败 → 返回 400 状态码

名称支持模糊匹配，如"双流"可匹配"双流区"，"成都"可匹配"成都市"。

## 配置说明

`config.json` 配置文件（不在 Git 中，从 `config.example.json` 复制）：

```json
{
  "default_location": {
    "province": "四川省",
    "city": "成都市",
    "district": "双流区"
  },
  "lark": {
    "app_id": "your_app_id",
    "app_secret": "your_app_secret",
    "remind_user_open_id": "your_open_id"
  },
  "reminder": {
    "enabled": true,
    "advance_minutes": 15,
    "interval_seconds": 60
  }
}
```

配置修改后**无需重启服务**，飞书 SET 指令写入后即时生效。
