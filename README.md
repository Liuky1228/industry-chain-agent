# 产业链分析 Agent（后端引擎 + 前端网站）

本仓库是「产业链分析 Agent」的**完整工程**，被 SkillHub 上的 `industry-chain-agent` Skill 自动安装和调用。

- **后端**：爬取公开研报 → LLM 提取企业关系 → 构建上/中/下游产业链 → 生成机构视角 Word 报告，并通过本地 API（默认 `http://localhost:8004`）对外服务。
- **前端网站**：`frontend/` 是一个本地网站（`http://localhost:3004`），提供发起任务 / 查看进度 / 历史记录 / 下载 Word 的可视化界面。

> **一句话结论**：下载项目 → 装好依赖 → 在 `.env` 填入**你自己的**密钥 → 同时跑起后端(8004)和前端(3004) → 浏览器开 `localhost:3004` 即可用。报告是一份生成在你自己电脑上的 Word 文档（`.docx`）。

---

## 目录结构

- `app/`：FastAPI 后端（`app/main.py` 为入口）
- `frontend/`：React + Vite 前端网站（`npm run dev` 启动，端口 3004）
- `requirements.txt`：Python 依赖
- `.env.example`：后端配置模板（复制为 `.env` 并填入你的密钥）
- `setup.sh` / `setup.ps1`：可选的一键后端依赖安装脚本（仍建议按下方详细步骤确保前端也装好）

---

## 一、前置准备（要先装哪些东西）

| 前置 | 干嘛用 | 必须吗 |
|---|---|---|
| **Python ≥ 3.10** | 跑后端程序 | ✅ 必须 |
| **Node.js ≥ 18** | 跑前端网站（localhost:3004） | ✅ 想用网站就必须；只想用接口可跳过 |
| **Git** | 用来"下载/更新"项目（命令行方式） | ⚠️ 可选——用"网页下载 ZIP"就不需要 |
| **自己的 API 密钥** | 报告要调用大模型，必须填你自己的 | ✅ 必须（不能共用作者的） |

---

## 二、下载项目到电脑

### 方式 A（最简单，推荐新手）—— 网页下载 ZIP
1. 浏览器打开 `https://github.com/Liuky1228/industry-chain-agent`
2. 点右上角绿色按钮 **「Code」→「Download ZIP」**
3. 解压后得到文件夹（Windows 解压为 `industry-chain-agent-main`；macOS 用 Safari 会自动解压为 `industry-chain-agent-main`；Linux 用 `unzip` 同样得到 `industry-chain-agent-main`）。建议放到桌面或家目录，好找。

### 方式 B（命令行，装了 Git 才用）
```bash
git clone https://github.com/Liuky1228/industry-chain-agent.git
```
> ⚠️ 国内连 GitHub 常连不上 → 改用方式 A 的 ZIP，或挂代理后 clone。

---

## 三、安装依赖（只需做一次）

下面所有命令都在**项目根目录**里执行（即进入解压出来的 `industry-chain-agent-main` 文件夹后）。

### 3.1 后端（Python）

**Windows（命令提示符 / PowerShell）：**
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
> 若 `pip` 很慢，换国内镜像：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

**macOS / Linux（终端）：**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
> macOS 若报 `externally-managed-environment`：说明用了系统自带 python3，请先确认上面用 `python3 -m venv` 建了 `.venv` 并 `source` 激活（命令行前面出现 `(.venv)`）后再 `pip install`；仍不行就从 python.org 重装干净 Python。
> 若 `pip` 很慢，加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`

激活成功后，命令行**最前面会出现 `(.venv)`** 字样 → 之后启动后端都要保持这个状态。

### 3.2 前端（Node）

在**已激活 `(.venv)` 的终端**里继续：
```bat
cd frontend
npm install
```
- 会下载前端零件，等 **1～3 分钟**（可能刷警告，正常）。
- 完成后 `cd ..` 回到项目根目录。

---

## 四、填入你自己的 API 密钥

> 报告依赖大模型，**必须填你自己的密钥**。作者已把硬编码 key 从仓库移除，仓库里没有任何可用密钥。

**Windows：**
1. 在项目根目录找到 `.env.example`，**复制一份**改名为 `.env`（⚠️"保存类型"选"所有文件"，别变成 `.env.txt`）。
2. 用记事本打开 `.env`，把 `DEEPSEEK_API_KEY=sk-请在此填写你自己的密钥` 改成 `DEEPSEEK_API_KEY=sk-你自己的密钥`，保存。

**macOS / Linux（推荐用终端，避免隐藏扩展名坑）：**
```bash
cp .env.example .env
open -e .env        # macOS 用文本编辑打开；Linux 用 nano .env
```
把 `DEEPSEEK_API_KEY=sk-请在此填写你自己的密钥` 改成你自己的 `sk-` 密钥，保存关闭（macOS `⌘+S`，Linux `Ctrl+O` 再 `Ctrl+X`）。

### 💡 关于"API 密钥"的几个关键要点（务必看）
- **变量名虽叫 `DEEPSEEK_API_KEY`，但默认其实用的是「阿里云百炼」的 Qwen 模型。** 看 `.env` 另外两行：
  ```
  DEEPSEEK_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
  DEEPSEEK_MODEL=qwen3.7-plus
  ```
  即：`.env` 默认已配好百炼地址和 Qwen 模型。**你只去阿里云百炼（https://bailian.console.aliyun.com/）申请一个 key，填进 `DEEPSEEK_API_KEY` 就能直接用**——最省事。
- **如果你有 DeepSeek / OpenAI / 硅基流动 / Moonshot 等别的「OpenAI 兼容」厂商的 key，也能用**，但要同时改 `.env` 这三行：
  ```
  DEEPSEEK_API_KEY=你的那家key
  DEEPSEEK_BASE_URL=那家的 OpenAI 兼容地址   # 例如 DeepSeek 是 https://api.deepseek.com/v1
  DEEPSEEK_MODEL=那家的模型名                # 例如 deepseek-chat
  ```
- ⚠️ **Anthropic / Claude 原生直接用不了**（协议不兼容）。非要用 Claude 需套 OpenAI 兼容网关（如 OpenRouter / LiteLLM）中转，新手不建议折腾。
- 改完 `.env` 后，要**重启后端**才会生效。

---

## 五、启动（需要开两个终端窗口）

要同时跑"后端"和"前端"，所以开**两个**终端窗口。

### 窗口 1：启动后端（8004）
在**激活了 `(.venv)` 的终端**里（若关了就重新 `cd` 进项目根目录并激活 venv）：
```bat
uvicorn app.main:app --host 0.0.0.0 --port 8004
```
- 若提示 `uvicorn` 不是命令，换成 `python -m uvicorn app.main:app --host 0.0.0.0 --port 8004`（macOS/Linux 用 `python3 -m uvicorn ...`）。
- 启动成功会一直刷日志。**这个窗口不要关。**
- 验证：浏览器开 `http://localhost:8004/api/health`，看到 `{"status":"ok",...}` 说明后端活了。

### 窗口 2：启动前端（3004，网站）
新开一个终端，进入前端目录：
```bat
cd frontend
npm run dev
```
- 出现 `Local: http://localhost:3004/` 字样 → 前端活了。**这个窗口也不要关。**

---

## 六、打开网站，体验功能

1. 浏览器打开 **`http://localhost:3004`** → 网站出来（和演示一致）。
2. 在网站里**发起任务**（输入产业名，如"光伏""锂电池""半导体"）。
3. 看进度变化 → 任务完成后在**历史记录**里**下载 Word 报告**（`.docx`）。
4. 报告实体文件也落在你电脑：`industry-chain-agent-main/data/reports/产业名_产业链分析报告_时间戳.docx`，可直接用 Word/WPS 打开。

> **备用方案（不装 Node 也能出报告）**：只要后端（窗口 1）起来了，浏览器开 `http://localhost:8004/docs` → `POST /api/tasks` 填 `{"industry_name":"光伏"}` → 拿到 `id` → `GET /api/tasks/{id}` 看进度 → 完成后 `GET /api/tasks/{id}/report` 直接下载 Word。这是没有网站时的纯接口用法。

---

## 七、用完怎么关

- 窗口 1（后端）：按 `Ctrl + C`
- 窗口 2（前端）：按 `Ctrl + C`
- 下次想再用，重复**第五步**启动即可（第三、四步只需做一次）。

---

## 八、如何获取后续更新

项目更新后，你不用重新下载整个项目、也不用重装依赖，只需刷新文件并重启相关服务：

- **用 `git clone` 装的用户**：在项目目录执行 `git pull`，自动同步所有改动，再重启服务。
- **用 ZIP 装的用户**：
  - 最稳：重新下载 ZIP，解压后**覆盖**原文件夹，再重启服务。
  - 若只是**个别前端文件改动**（如某个 `.jsx`），也可只去 GitHub 下载那个文件替换本地同名文件，然后重启前端（甚至只刷新浏览器，Vite 开发模式带热更新）。
- ⚠️ **什么时候"只换一个文件不够"**：改动涉及 `package.json`/`package-lock.json` → 需重跑 `npm install`；涉及 `app/` 后端 `.py` → 需重启后端（且若 `requirements.txt` 变了要先 `pip install -r requirements.txt`）；新增了文件 → 必须连新文件一起拿（建议用 `git pull` 或整包覆盖）。

---

## 九、排错速查表

| 现象 | 处理 |
|---|---|
| `python` / `python3` 不是命令 | Windows 重装 Python 时勾 **Add Python to PATH**；macOS 用 `python3`；Linux `sudo apt install python3` |
| `externally-managed-environment` 错误 | 用 `python3 -m venv .venv` 建虚拟环境并 `source` 激活后再 `pip install` |
| `pip install` 慢/超时 | 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `uvicorn` 不是命令 | 改用 `python -m uvicorn app.main:app --host 0.0.0.0 --port 8004`（macOS/Linux 用 `python3`） |
| `npm` 不是命令 | 没装 Node.js（≥18），去 nodejs.org 装 |
| `npm install` 报 EACCES（macOS/Linux） | 别用 `sudo` 硬来；重装一次 Node（官方 `.pkg` 方式）最省事 |
| `git clone` 失败 / 连不上 GitHub | 改用"网页下载 ZIP"；或挂代理后 clone |
| 网站 `localhost:3004` 打不开 | 前端没起或没装依赖：回第三步 `npm install` 再第五步 `npm run dev`；确认窗口 2 出现 `Local: http://localhost:3004/` |
| 后端 `localhost:8004` 打不开 | 后端没起或依赖没装：回第三步；确认窗口 1 刷日志且无报错 |
| 端口 8004 / 3004 被占用 | 关掉占端口的程序再启动；Windows 用 `netstat -ano \| findstr :8004`，macOS/Linux 用 `lsof -i :8004` 查 PID 后 `kill -9 <PID>` |
| 任务一直 `failed` / 报错含"配额""unauthorized" | `.env` 里的密钥无效或没余额 → 换你自己的有效 Key（第四步），并重启后端 |
| 网站能打开但发任务没反应 | 后端没起或 8004 不对；确认窗口 1 日志正常、且 `http://localhost:8004/api/health` 返回 ok |
| `.env` 改了不生效 | 改完 `.env` 必须**重启后端** |

---

## 主要 API

- `POST /api/tasks`：创建分析任务
- `GET /api/tasks/{id}`：查询任务详情
- `GET /api/tasks/{id}/report`：下载 Word 报告
- `GET /api/health`：健康检查

---

## 一键安装（推荐：通过 Skill 自动完成）

若你通过 SkillHub 的 `industry-chain-agent` Skill 使用，Skill 会自动执行：
`git clone` 本仓库 → 建虚拟环境 → `pip install` 依赖 → 生成 `.env`，
你只需在 `.env` 里填入自己的 `DEEPSEEK_API_KEY` 即可。

> ⚠️ `.env` 含你的密钥，已被 `.gitignore` 忽略，请勿提交。
