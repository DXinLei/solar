# 倪派紫微斗数真太阳时 API

基于 **FastAPI + ephem** 的真太阳时计算服务，集成**飞书机器人**与**子午流注十二时辰养生提醒**。

## 功能特性

- 🌞 **真太阳时计算** — 基于 ephem 天文库，自动含均时差修正
- 🕐 **十二时辰判定** — 支持倪派晚子时规则（23:00-00:00 为晚子时）
- ⏰ **夏令时修正** — 自动处理 1986-1991 年中国夏令时
- 🤖 **飞书机器人** — 支持 `/set`、`/get`、`/help` 斜杠命令
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

### 方式一：本地运行（使用虚拟环境）

```bash
# 1. 进入项目目录
cd solar

# 2. 创建并激活虚拟环境（首次）
python -m venv .venv

# Windows 激活虚拟环境
source .venv/Scripts/activate
# 或: .venv\Scripts\activate

# macOS / Linux 激活虚拟环境
# source .venv/bin/activate

# 3. 安装依赖（首次，或依赖有更新时）
pip install -e .

# 4. 准备数据文件
# 确保 data/ 目录下包含以下文件：
#   - ok_data_level3.csv
#   - ok_data_level4.csv
#   - ok_geo.csv（160MB，需手动放置）

# 5. 创建配置文件（首次）
cp config.example.json config.json
# 编辑 config.json 填入飞书 App ID / App Secret / open_id

# 6. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> **提示**：每次重新打开终端后，需要先激活虚拟环境（第 2 步）再启动服务。

### 方式二：Docker 部署（推荐）

```bash
# 1. 准备数据文件
# 确保 data/ok_geo.csv 已放置（160MB，不在 Git 中）

# 2. 创建配置文件（首次）
cp config.example.json config.json
# 编辑 config.json 填入飞书 App ID / App Secret / open_id

# 3. 构建并启动
docker compose up -d

# 4. 查看日志
docker compose logs -f
```

### Git 拉取更新后重启

```bash
# 1. 拉取最新代码
git pull

# 2. 如果依赖有变化，重新安装
# 本地运行：
source .venv/Scripts/activate   # 先激活虚拟环境
pip install -e .                # 更新依赖

# Docker：
docker compose build --no-cache  # 重新构建镜像
# 或增量构建（更快）：
docker compose build

# 3. 重启服务
# 本地运行：重新执行启动命令即可（Ctrl+C 停止旧进程）
# uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Docker：
docker compose down              # 停止旧容器
docker compose up -d             # 启动新容器

# 或一步重启（推荐）：
docker compose up -d --build
```

> **提示**：如果只是代码变更（不涉及数据文件或配置），本地运行模式下 `--reload` 会自动热重载，无需手动重启。Docker 模式下需重新构建并启动。

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
│   ├── main.py                 # FastAPI 入口 + 完整 REST 路由定义
│   ├── config.py               # 配置热读 + 原子写入 + 渠道开关
│   ├── data_loader.py          # CSV 数据加载 + 地址三级降级匹配
│   ├── location_service.py     # 统一位置管理服务（校验 + 落盘 + 调度器热重载）
│   ├── solar_calculator.py     # 真太阳时计算 + 逆向推算
│   ├── schemas.py              # Pydantic v2 数据模型定义
│   ├── notifier.py             # 抽象通知分发层（解耦飞书 REST / Webhook）
│   ├── lark_bot.py             # 可选飞书机器人（WS 监听 + 斜杠命令交互）
│   ├── scheduler.py            # 精确触发调度器（36触发点/日 + 动态重载）
│   └── health_guide.py         # 养生消息构建与时辰查询
├── tests/                      # 服务端与解耦功能完整测试套件
└── README.md
```

## API 接口

### 1. GET /api/solar-time

查询指定地点的真太阳时信息（含太阳空间视位置与定向参数）。

**请求参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| province | string | config.json | 省份名称，不传使用配置文件默认值。省/市/区必须**全部传入**或**全部省略** |
| city | string | config.json | 同上 |
| district | string | config.json | 同上 |
| bj_time | string | 当前时间 | 北京时间 YYYY-MM-DD HH:MM:SS |

### 2. GET /api/solar-position

**太阳地平视位置与高精度定向接口**（专供安卓 App、网页实景罗盘、建筑采光与真北校准使用）。

返回太阳方位角（Azimuth）、仰角（Altitude）、日影反向朝向角（Shadow Azimuth，用于量角器/地砖直接对齐）以及定向文字指引。

**响应示例：**
```json
{
  "input": {
    "province": "四川",
    "city": "成都",
    "district": "双流区",
    "bj_time": "2026-11-02 17:09:24"
  },
  "standard_bj_time": "2026-11-02 17:09:24",
  "true_solar_time": "16:15:12",
  "solar_shichen": "申时",
  "solar_position": {
    "azimuth": 244.21,
    "altitude": 12.59,
    "shadow_azimuth": 64.21,
    "direction": "西南偏西",
    "shadow_direction": "东北偏东",
    "is_visible": true,
    "orientation_guide": "当前太阳位于【西南偏西】(244.21°)，仰角 12.59°。面向太阳时，真北位于左侧偏后 244.2°；垂直物体日影严格指向【东北偏东】(64.21°)。"
  }
}
```

### 3. GET /api/location

获取当前服务配置的默认地理位置、中心点经纬度及匹配精度。

**响应示例：**
```json
{
  "message": "ok",
  "data": {
    "province": "四川",
    "city": "成都",
    "district": "双流区",
    "longitude": 103.92342,
    "latitude": 30.574884,
    "level": "district"
  }
}
```

### 4. POST /api/location

更新默认地理位置。自动校验地址有效性、原子写入 `config.json`，并**即时重新规划 APScheduler 36 个触发任务**，无需重启服务。

**请求 Body（JSON）：**
```json
{
  "province": "广东省",
  "city": "广州市",
  "district": "天河区"
}
```

**响应示例：**
```json
{
  "message": "默认地理位置已更新，调度器任务已同步刷新",
  "data": {
    "province": "广东",
    "city": "广州",
    "district": "天河区",
    "longitude": 113.361597,
    "latitude": 23.124817,
    "level": "district"
  }
}
```

### 5. GET /api/health-guide

查询《黄帝内经》十二时辰养生指南。
- 不传参数：返回全部 12 个时辰的养生数据；
- 传 `?shichen=午时`：返回该时辰的理论依据、核心宜做、禁忌、穴位及养护方法。

### 6. GET /api/health-guide/current

根据当前生效的默认位置与服务器当前实时真太阳时，动态计算并返回当前所处时辰的养生指导与下一个时辰预告。

### 7. GET /api/status

获取服务端整体运行状态：当前位置、各通知渠道启用状态（飞书/Webhook）、飞书长连接机器人运行状态、调度器运行状态及当前已注册的任务数量。

### 8. POST /api/health-guide/notify-test

立即手动触发一次当前时辰的养生提醒测试通知，用于检验已启用的通知渠道（飞书推送 / Webhook 推送）是否联通正常。

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

在飞书中向机器人发送**斜杠命令**（不区分大小写）即可使用：

### 可用命令

| 命令 | 说明 |
|------|------|
| **`/set 省,市,区`** | 设置默认地理位置（支持中英文逗号） |
| **`/get`** | 查询当前实时真太阳时 |
| **`/help`** | 显示所有可用命令 |

### 命令示例

```
/set 四川,成都,双流区    ✅ 设置默认位置为成都双流区
/set 广东，广州，天河区   ✅ 支持中文逗号
/GET                     ✅ 查询当前真太阳时
/Help                    ✅ 显示帮助信息
```

### `/get` 响应示例

非子时时段：

```
📍 四川省 成都市 双流区
📌 匹配精度: 区级
🌐 经纬度: 103.92365, 30.57447

🌞 真太阳时: 10:53:17
🕐 时辰: 巳时
📅 日期: 2026-07-13

⏰ 标准北京时间: 12:00:00
```

子时时段（23:00-01:00）：

```
📍 四川省 成都市 双流区
📌 匹配精度: 区级
🌐 经纬度: 103.92365, 30.57447

🌞 真太阳时: 23:35:12
🕐 时辰: 子时 (晚子时)
📅 日期: 2026-07-12

⏰ 标准北京时间: 2026-07-13 00:05:00
```

> **说明**：子时（23:00-01:00）会显示 `(早子时)` 或 `(晚子时)`。晚子时（23:00~00:00）日期自动沿用前一天，早子时（00:00~01:00）按当天计算。

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
    "enabled": false,
    "app_id": "your_app_id",
    "app_secret": "your_app_secret",
    "remind_user_open_id": "your_open_id"
  },
  "webhook": {
    "enabled": false,
    "url": "https://your-service.com/api/webhook"
  },
  "reminder": {
    "enabled": true,
    "advance_minutes": 15,
    "interval_seconds": 60
  }
}
```

### 独立部署与一键停用飞书

- **完全屏蔽飞书（纯 API 模式）**：
  将 `lark.enabled` 设为 `false`，服务启动时将**完全不连接 WebSocket，不启动机器人线程，不向飞书推送任何信息**，零多余警告与资源占用。
- **配置修改无需重启服务**：
  通过 HTTP `POST /api/location` 或飞书 `/set` 命令修改位置后，不仅配置文件原子更新，**后台调度器也会自动清空旧任务并按新坐标重新规划 36 个触发时刻**。
- **通用 Webhook 支持**：
  若想对接其他系统（企业微信、钉钉、外部自动化平台），只需开启 `webhook.enabled: true` 并填入接收 URL，调度器触发时将自动向该 URL 推送 JSON 格式养生消息。

## 更新日志

### v1.1.0 — 架构彻底解耦与纯净服务端重构

- 🔌 **飞书模块完全解耦** — 飞书从核心依赖降级为可选外接插件，通过 `lark.enabled: false` 可实现一键彻底停用；
- 🌐 **补齐 REST 写入与位置管理 API** — 新增 `GET /api/location` 与 `POST /api/location`，服务端不再依赖飞书修改配置；
- 🔄 **调度器热重载联动** — 通过统一 `location_service` 更新位置后，自动触发 APScheduler 重新计算并挂载 36 个触发时刻；
- 📣 **抽象多渠道通知分发器 (`notifier.py`)** — 切断调度器对飞书代码的硬依赖，支持飞书 REST、通用 Webhook 及静默无通知模式；
- 🌿 **养生指南 API 化** — 新增 `GET /api/health-guide` 与 `GET /api/health-guide/current`，前端或移动端可直接调用；
- 📊 **系统运行状态接口** — 新增 `GET /api/status` 与 `POST /api/health-guide/notify-test` 测试触发接口；
- 🧪 **完整单元测试覆盖** — 新增 `tests/test_server.py` 与 `tests/test_lark_bot.py`。

### v0.2.0 — 飞书机器人斜杠命令重构

- ✨ **新增 `/help` 命令** — 列出所有可用命令
- ✨ **新增 `/get` 命令** — 查询当前实时真太阳时（含地点、匹配精度、经纬度、时辰、排盘日期）
- 🔄 **`SET` 改为 `/set`** — 标准化为斜杠命令格式
- 🧠 **未知命令提示** — 输入未知 `/xxx` 命令时自动提示使用 `/help`
- 📖 **README 更新** — 新增虚拟环境激活说明、Docker 使用指引、Git 拉取更新重启流程
