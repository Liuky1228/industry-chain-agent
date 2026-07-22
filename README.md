# 产业链分析 Agent（后端引擎 + 前端网站）

本仓库是「产业链分析 Agent」的**完整工程**，被 SkillHub 上的 `industry-chain-agent` Skill 自动安装和调用。
后端负责：爬取公开研报 → LLM 提取企业关系 → 构建上/中/下游产业链 → 生成 8 章机构视角 Word 报告，
并通过本地 API（默认 `http://localhost:8004`）对外提供服务；
`frontend/` 是一个本地网站（`http://localhost:3004`），提供发起任务 / 查看进度 / 历史记录 / 下载 Word 的可视化界面。

## 目录结构
- `app/`：FastAPI 后端（`app/main.py` 为入口）
- `frontend/`：React + Vite 前端网站（`npm run dev` 启动，端口 3004）
- `requirements.txt`：Python 依赖
- `.env.example`：后端配置模板（复制为 `.env` 并填入你的密钥）

## 一键安装（推荐：通过 Skill 自动完成）
若你通过 SkillHub 的 `industry-chain-agent` Skill 使用，Skill 会自动执行：
`git clone` 本仓库 → 建虚拟环境 → `pip install` 依赖 → 生成 `.env`，
你只需在 `.env` 里填入自己的 `DEEPSEEK_API_KEY` 即可。

## 手动安装
```bash
git clone https://github.com/Liuky1228/industry-chain-agent.git
cd industry-chain-agent
# Windows
powershell -ExecutionPolicy Bypass -File setup.ps1
# macOS / Linux
bash setup.sh
# 然后编辑 .env，填入你的 DEEPSEEK_API_KEY
```

## 手动启动（后端）

需先安装 Python 依赖（见上方「手动安装」）。然后在仓库根目录执行：
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8004
```

## 前端网站（可选，需 Node.js ≥ 18）

前端是一个本地网站，提供图形化界面（发起任务 / 进度 / 历史 / 下载报告）。
它把 `/api` 请求代理到本机后端的 `http://localhost:8004`，**本地使用无需任何额外配置**。

```bash
# 1) 安装一次 Node.js ≥ 18（https://nodejs.org ），自带 npm
# 2) 在 frontend 目录安装依赖（仅首次）
cd frontend
npm install
# 3) 启动前端（保持窗口开着），默认 http://localhost:3004
npm run dev
```

启动后浏览器打开 `http://localhost:3004` 即可使用。
> 注意：前端 `npm run dev` 与前端的 `uvicorn` 后端需**同时运行**（前端只占 3004，后端占 8004）。

## 主要 API
- `POST /api/tasks`：创建分析任务
- `GET /api/tasks/{id}`：查询任务详情
- `GET /api/tasks/{id}/report`：下载 Word 报告
- `GET /api/health`：健康检查

> ⚠️ `.env` 含你的密钥，已被 `.gitignore` 忽略，请勿提交。
