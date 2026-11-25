# ZZU WhatWeNeed · 郑州大学校园生活站

> a web to live in zzu

基于开源项目 [TorCroft/ZZU-API](https://github.com/TorCroft/ZZU-API) 整合重构的郑州大学移动校园一站式网页端，支持多用户会话、手机与桌面响应式布局，并可直接部署至 **Render** 免费云服务。

## 功能特性

整合了 `TorCroft/ZZU-API` 提供的全部核心接口：

- **统一认证登录**：支持学号 + 移动校园密码登录，或直接粘贴已有 `UserToken` 登录；服务端仅在内存中以加密签名 Cookie 维护会话，**不落盘保存明文密码或校园卡密码**。
- **演示模式**：无需输入真实学号即可一键体验全部页面与交互。
- **空教室查询**：支持按校区、教学楼、日期、楼层与多选节次（第 1~10 节）筛选空闲教室，并提供全天 10 节占用可视化条。
- **个人课表**：自动拉取学期列表与作息时间，支持按周切换（上一周 / 本周 / 下一周）查看 7×10 网格课表。
- **成绩查询**：支持全量成绩拉取、按学期筛选、关键词搜索，以及课程数、总学分、加权绩点参考统计。
- **期末考试**：按学期查询考试时间、地点、座位号，并自动计算考试倒计时。
- **校园卡与宿舍电费**：实时查询校园卡余额、绑定宿舍剩余电量，支持手动刷新 `ECardAccessToken`，并提供带二次确认弹窗的**卡对卡转账 (C2C)**。
  - *注：根据上游 `TorCroft/ZZU-API` 说明，宿舍电费充值采用 RSA 加密且无私钥，故不包含电费充值功能。*

---

## 一键部署到 Render（推荐）

1. 登录 [Render](https://render.com/)，点击 **New +** → **Blueprint**（或 **Web Service**）。
2. 关联本仓库 `Simoon1218/ZZUweb_WhatWeNeed`。
3. Render 会自动识别仓库内的 [`render.yaml`](./render.yaml) 和 [`Dockerfile`](./Dockerfile)：
   - `SESSION_SECRET` 会自动生成。
   - 健康检查路径为 `/api/health`。
   - 如遇到海外机房访问郑州大学上游接口超时，可在环境变量中选填 `UPSTREAM_PROXY`。
4. 等待构建完成后，即可通过 Render 分配的 HTTPS 网址直接访问。

> 提示：Render Free 实例在 15 分钟无访问后会自动休眠，首次打开时等待约 30~60 秒唤醒即可；实例重启后内存会话会清空，重新登录即可继续使用。

---

## 本地运行

需要 Python 3.11+：

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器访问 `http://localhost:8000`。

### Docker 运行

```bash
docker build -t zzuweb-whatweneed .
docker run -d --name zzuweb-whatweneed -p 8000:8000 zzuweb-whatweneed
```

---

## 环境变量说明

| 变量名 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `PORT` | `8000` | 服务监听端口（Render 自动注入） |
| `SESSION_SECRET` | 启动随机生成 | HttpOnly 会话 Cookie 签名密钥 |
| `SESSION_TTL_HOURS` | `24` | 会话有效期（小时） |
| `REQUEST_TIMEOUT` | `15` | 请求郑州大学上游接口的超时时间（秒） |
| `UPSTREAM_PROXY` | 空 | 可选 HTTP/HTTPS 代理地址 |
| `COOKIE_SECURE` | `auto` | 是否强制 Cookie `Secure` 标志 |

---

## 项目结构

```text
.
├── app/
│   ├── config.py        # 环境变量与代理配置
│   ├── session.py       # 多用户内存会话与 HMAC Cookie 校验
│   ├── zzu_client.py    # 基于 TorCroft/ZZU-API 重构的多用户客户端
│   ├── demo_data.py     # 演示模式模拟数据
│   └── main.py          # FastAPI 路由与静态页面托管
├── static/
│   ├── index.html       # 响应式单页应用入口
│   ├── styles.css       # 郑州大学主题风格 + 深浅色模式样式
│   └── app.js           # 前端状态管理与 6 大校园模块交互
├── Dockerfile           # Render / Docker 容器构建文件
├── render.yaml          # Render Blueprint 一键部署配置
├── requirements.txt     # Python 依赖
└── .env.example         # 环境变量示例
```

## 致谢

- 校园 API 接口逆向与协议参考：[TorCroft/ZZU-API](https://github.com/TorCroft/ZZU-API)
