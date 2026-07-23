# 没有 WorkBuddy，纯用 GitHub 项目体验「产业链分析网站」——零基础完整指南

> 适用对象：一个**没有安装 WorkBuddy**、只想把你发布在 GitHub 上的项目下载到自己电脑上、用浏览器打开 `http://localhost:3004` 网站来用的人。
> 结论先说：这个 GitHub 仓库 **既有后端引擎、也有前端网站**。下载到你电脑、装好依赖、填上你自己的密钥，跑起来后浏览器开 `localhost:3004` 就是完整网站；报告是一份 Word 文档（`.docx`）。

---

## 〇、先搞清楚：要装哪些东西（前置清单）

| 前置 | 干嘛用 | 必须吗 |
|---|---|---|
| **Python ≥ 3.10** | 跑后端程序 | ✅ 必须 |
| **Node.js ≥ 18** | 跑前端网站（localhost:3004） | ✅ 想用网站就必须；只想用接口可跳过 |
| **Git** | 用来"下载"项目（命令行方式） | ⚠️ 可选——用"网页下载 ZIP"就不需要 |
| **自己的 API 密钥** | 报告要调用大模型，必须填你自己的 | ✅ 必须（不能共用作者的） |

---

## 第 0 步：检查电脑装了没（装没装、没装怎么办）

### Windows 怎么检查
1. 按 `Win` 键，输入 `cmd`，回车，打开"命令提示符"。
2. 逐行输入下面命令（每行回车）：
   ```bat
   python --version
   node -v
   npm -v
   git --version
   ```
3. 看结果：
   - 显示版本号（如 `Python 3.12.1`、`v22.22.2`、`10.9.7`、`git version 2.45.0`）→ ✅ 已装。
   - 显示`'python' 不是内部或外部命令`之类 → ❌ 没装，去下面装。

### Mac 怎么检查
1. 打开"启动台"→ 搜"终端" → 打开。
2. 输入：
   ```bash
   python3 --version
   node -v
   npm -v
   git --version
   ```
   > ⚠️ Mac 上命令叫 `python3`，不是 `python`。
3. 显示版本号 → 已装；`command not found` → 没装。

### 没装怎么办（下载地址，按自己系统装）
- **Python**（≥3.10）：https://www.python.org/downloads/
  - Windows：安装时**务必勾选 "Add Python to PATH"**（最容易漏，漏了后面命令找不到 python）。
  - Mac：下载 macOS 安装包一路下一步。
- **Node.js**（≥18，LTS 版）：https://nodejs.org
  - 装完 `node` 和 `npm` 会一起装好。前端网站需要它。
- **Git**（可选）：https://git-scm.com/download/win （Windows）；Mac 在终端输 `git --version` 弹窗按提示装即可。
  - 如果你用下面的"网页下载 ZIP"方式，可以**不装 Git**。
- **API 密钥**（必填，自己的）：
  - 打开 https://bailian.console.aliyun.com/ （阿里云百炼，用你自己的账号登录）。
  - 右上角头像 → **API Key 管理** → 创建 / 查看 → 复制那一长串以 `sk-` 开头的密钥。
  - 这是**你自己的**，必须自己申请，不能抄作者的。

---

## 第 1 步：把项目下载到电脑

### 方式 A（最简单，推荐不懂命令行的用户）—— 网页下载 ZIP
1. 浏览器打开 `https://github.com/Liuky1228/industry-chain-agent`
2. 点右上角绿色按钮 **「Code」→「Download ZIP」**
3. 下载完成后**解压**，得到一个文件夹 `industry-chain-agent`（建议放桌面，好找）。

### 方式 B（命令行）
在终端里执行：
```bash
git clone https://github.com/Liuky1228/industry-chain-agent.git
```
> ⚠️ 国内连 GitHub 常报 `Connection reset` / 连不上 → 见文末「排错」用代理或 SSH，或干脆改用方式 A 的 ZIP。

---

## 第 2 步：准备后端（Python 依赖，只做一次）

打开终端，进入项目文件夹（路径按你实际放的位置改）：
- Windows：`cd C:\Users\你的用户名\Desktop\industry-chain-agent`
- Mac：`cd ~/Desktop/industry-chain-agent`

然后执行（**一行一行来**）：

**Windows：**
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
**Mac / Linux：**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
- 如果 `pip install` 很慢或卡住，换国内镜像（把上面那行换成）：
  ```bash
  pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  ```
- 装完后，命令行**最前面会出现 `(.venv)`** 字样 → 说明进入了虚拟环境，成功。**之后启动后端都要保持这个状态**。

---

## 第 3 步：准备前端（Node 依赖，网站需要，只做一次）

在"第 2 步那个已激活 `.venv` 的终端"里继续输入：
```bat
cd frontend
npm install
```
- 这步会下载前端零件，需要等 **1～3 分钟**。
- 完成后 `cd ..` 回到项目根目录。
- > 如果你确定**只想用接口出报告、完全不要网站**，可以跳过这步；但既然要"体验网站"，这步必做。

---

## 第 4 步：填入你自己的 API 密钥

1. 在项目根目录找到 `.env.example` 文件，**复制一份**，改名为 `.env`
   （⚠️ Windows 上"保存类型"选"所有文件"，别让它变成 `.env.txt`）。
2. 用记事本打开 `.env`，把这一行：
   ```
   DEEPSEEK_API_KEY=sk-请在此填写你自己的密钥
   ```
   改成（等号后面换成你自己申请的 `sk-` 密钥）：
   ```
   DEEPSEEK_API_KEY=sk-你自己的密钥
   ```
   其余内容**不要动**，保存关闭。
- 这个 `.env` 里有你的密钥，已被 `.gitignore` 忽略，不会上传，放心。

### 💡 关于"API 密钥"的几个关键要点（务必看）

- **变量名虽然叫 `DEEPSEEK_API_KEY`，但默认其实用的是「阿里云百炼」的 Qwen 模型。** 看 `.env` 另外两行就明白了：
  ```
  DEEPSEEK_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
  DEEPSEEK_MODEL=qwen3.7-plus
  ```
  也就是说：**`.env` 里默认已经配好百炼地址和 Qwen 模型了。你只去阿里云百炼（https://bailian.console.aliyun.com/）申请一个 key，填进 `DEEPSEEK_API_KEY` 就能直接用**——这是最省事的方式。
- **如果你手里是 DeepSeek / OpenAI / 硅基流动 / Moonshot 等别的「OpenAI 兼容」厂商的 key，也能用**，但要同时改 `.env` 这三行：
  ```
  DEEPSEEK_API_KEY=你的那家key
  DEEPSEEK_BASE_URL=那家的 OpenAI 兼容地址   # 例如 DeepSeek 是 https://api.deepseek.com/v1
  DEEPSEEK_MODEL=那家的模型名                # 例如 deepseek-chat
  ```
- ⚠️ **Anthropic / Claude 原生直接用不了**（协议不兼容）。非要用 Claude，得套一个 OpenAI 兼容网关（如 OpenRouter / LiteLLM）中转，新手不建议折腾。
- ⚠️ **必须用你自己的 key，不能抄作者的**（作者已把硬编码 key 从仓库移除，仓库里没有任何可用密钥）。
- 改完 `.env` 后，要**重启后端**（关掉窗口 1 再重跑第 5 步）才会生效。

---

## 第 5 步：启动（需要开两个终端窗口）

要同时跑"后端"和"前端"，所以开**两个**终端窗口。

### 窗口 1：启动后端（8004）
在**激活了 `.venv` 的终端**里（如果关了就重新 `cd` 进项目根目录并 `.venv\Scripts\activate` / `source .venv/bin/activate`）：
```bat
uvicorn app.main:app --host 0.0.0.0 --port 8004
```
- 如果提示 `uvicorn 不是命令`，换成：
  ```bat
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8004
  ```
- 启动成功后会一直刷日志。**这个窗口不要关**。
- 验证：浏览器打开 `http://localhost:8004/api/health`，看到 `{"status":"ok",...}` 就说明后端活了。

### 窗口 2：启动前端（3004，网站）
新开一个终端，进入项目的前端目录：
- Windows：`cd C:\Users\你的用户名\Desktop\industry-chain-agent\frontend`
- Mac：`cd ~/Desktop/industry-chain-agent/frontend`
```bat
npm run dev
```
- 出现 `Local: http://localhost:3004/` 之类字样 → 前端活了。**这个窗口也不要关**。

---

## 第 6 步：打开网站，体验功能

1. 浏览器打开 **`http://localhost:3004`** → 网站出来了（和作者演示的一模一样）。
2. 在网站里**发起一个任务**（输入产业名，如"光伏""锂电池""半导体"）。
3. 看进度条 / 状态变化 → 任务完成后在**历史记录**里**下载 Word 报告**（`.docx`）。
4. 报告实体文件也落在你电脑的项目目录里：
   `industry-chain-agent/data/reports/产业名_产业链分析报告_时间戳.docx`，可直接用 Word/WPS 打开。

> **备用方案（不装 Node 也能出报告）**：只要后端（窗口 1）起来了，浏览器开 `http://localhost:8004/docs` → 找到 `POST /api/tasks` 点 Try it out → 填 `{"industry_name":"光伏"}` → Execute 拿到 `id` → `GET /api/tasks/{id}` 看进度 → 完成后 `GET /api/tasks/{id}/report` 直接下载 Word。这就是没有网站时的纯接口用法。

---

## 第 7 步：用完怎么关

- 窗口 1（后端）：按 `Ctrl + C`
- 窗口 2（前端）：按 `Ctrl + C`
- 下次想再用，重复**第 5 步**启动即可（第 2、3、4 步只需做一次）。

---

## 排错速查表

| 现象 | 处理 |
|---|---|
| `git clone` 失败 / Connection reset | 国内墙 GitHub：① 改用"网页下载 ZIP"（第 1 步方式 A）；② 或加代理 `git config --global http.proxy http://127.0.0.1:你的代理端口`；③ 或配 SSH 后 `git clone git@github.com:Liuky1228/industry-chain-agent.git` |
| `python` 不是命令 | Windows 重装 Python 时勾 **Add Python to PATH**；Mac 用 `python3` |
| `pip install` 慢/超时 | 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `uvicorn` 不是命令 | 改用 `python -m uvicorn app.main:app --host 0.0.0.0 --port 8004` |
| `npm` 不是命令 | 没装 Node.js，回第 0 步装（≥18） |
| 网站 `localhost:3004` 打不开 | 前端没起或没装依赖：回第 3 步 `npm install` 再第 5 步 `npm run dev`；确认窗口 2 出现 `Local: http://localhost:3004/` |
| 后端 `localhost:8004` 打不开 | 后端没起或依赖没装：回第 2 步；确认窗口 1 刷日志且无报错 |
| 端口 8004 / 3004 被占用 | 关掉其他占端口的程序再启动；或改启动命令里的端口（前端端口还要同步改 `frontend/vite.config.js` 的 `port` 和代理 `target`） |
| 任务一直 `failed` / 报错含"配额""unauthorized" | `.env` 里的密钥无效或没余额 → 换你自己的有效 Key（第 4 步） |
| 网站能打开但发任务没反应 | 后端没起或 8004 不对；确认窗口 1 日志正常、且 `http://localhost:8004/api/health` 返回 ok |

---

## 一句话总结给使用者
装好 **Python + Node** → 下载项目（ZIP 或 git）→ 建虚拟环境装后端依赖、前端 `npm install` → 在 `.env` 填**你自己的** `sk-` 密钥 → 两个窗口分别跑后端(8004)和前端(3004) → 浏览器开 `localhost:3004` 用网站。报告是一份生成在你自己电脑上的 Word 文档。
