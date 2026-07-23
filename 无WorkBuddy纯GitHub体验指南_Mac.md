# 没有 WorkBuddy，纯用 GitHub 项目在 Mac 上体验「产业链分析网站」——零基础超详细指南

> 适用对象：一台 **Mac 电脑**（macOS）、**没有安装 WorkBuddy**、只想把你发布在 GitHub 上的项目下载到自己电脑、用浏览器打开 `http://localhost:3004` 网站来用的人。
> 结论先说：这个 GitHub 仓库 **既有后端引擎、也有前端网站**。下载到你电脑、装好依赖、填上你自己的密钥，跑起来后浏览器开 `localhost:3004` 就是完整网站；报告是一份 Word 文档（`.docx`）。
> 本指南全程针对 **Mac**，命令都用 Mac 终端写法（注意 Mac 上 Python 命令叫 `python3`，不是 `python`）。

---

## 〇、先搞清楚：要装哪些东西（前置清单）

| 前置 | 干嘛用 | 必须吗 |
|---|---|---|
| **Python ≥ 3.10** | 跑后端程序（建议用 python.org 装的，自带 pip） | ✅ 必须 |
| **Node.js ≥ 18** | 跑前端网站（localhost:3004） | ✅ 想用网站就必须；只想用接口可跳过 |
| **Git** | 用来"下载"项目（命令行方式） | ⚠️ 可选——用"网页下载 ZIP"就不需要 |
| **自己的 API 密钥** | 报告要调用大模型，必须填你自己的 | ✅ 必须（不能共用作者的） |

---

## 第 0 步：检查 + 安装（Mac 专属）

### 0.1 怎么打开"终端"（三种方式，任选）
- **方式一（最常用）**：按 `⌘（Command） + 空格` 打开 Spotlight，输入「终端」或「Terminal」，回车。
- **方式二**：打开「访达（Finder）」→「应用程序」→「实用工具」→「终端」。
- **方式三**：打开「启动台（Launchpad）」，搜「终端」。

> 后面所有带 `$` 开头的命令，都是在终端里输入、按回车执行的。不用把 `$` 也打进去。

### 0.2 检查装了没
在终端里逐行输入（每行回车）：
```bash
python3 --version
node -v
npm -v
git --version
```
- 显示版本号（如 `Python 3.12.1`、`v22.22.2`、`10.9.7`、`git version 2.45.0`）→ ✅ 已装。
- 显示 `command not found: python3` 之类 → ❌ 没装，按下面装。

> ⚠️ **重要**：macOS 系统自带一个 `python3`（来自 Xcode 命令行工具），但它经常**没有 pip** 或版本偏旧，而且 newer macOS 会把它标记为"外部管理环境"，直接 `pip install` 会报错。所以**强烈建议从 python.org 另装一个干净的 Python**（见下），不要依赖系统那个。

### 0.3 没装怎么办（下载地址）
- **Python（≥3.10，推荐从官网装）**：https://www.python.org/downloads/macos/
  - 下载 **macOS 64-bit universal2 installer**（Intel 和 Apple 芯片都兼容）。
  - 双击 `.pkg` 一路「继续 / 同意 / 安装」即可。装完 `python3 --version` 应能看到新版本。
- **Node.js（≥18，LTS 版）**：https://nodejs.org
  - 点「LTS」大按钮下载 `.pkg`，双击安装。`node` 和 `npm` 会一起装好。
- **Git（可选）**：
  - 在终端输入 `git --version`，若弹出「安装命令行开发者工具」点「安装」即可（系统自带方式）。
  - 或装 Homebrew 后 `brew install git`（见下）。
- **（可选但推荐）Homebrew**：Mac 上的"软件包管理器"，能一条命令装 Python/Node/Git。
  - 终端粘贴回车：
    ```bash
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    ```
  - 装完后可以：
    ```bash
    brew install python node git
    ```
  - 如果你不熟悉命令行，用上面的官网 `.pkg` 手动装也完全没问题，不用强求 Homebrew。

### 0.4 申请你自己的 API 密钥（必填）
- 打开 https://bailian.console.aliyun.com/ （**阿里云百炼**，用你自己的账号登录；没有就注册一个）。
- 右上角头像 → **API Key 管理** → 创建 / 查看 → 复制那一长串以 `sk-` 开头的密钥。
- 这是**你自己的**，必须自己申请，**不能抄作者的**（作者已把硬编码 key 从仓库移除，仓库里没有任何可用密钥）。

---

## 第 1 步：把项目下载到 Mac

### 方式 A（最简单，推荐新手）—— 网页下载 ZIP
1. 浏览器（Safari / Chrome 都行）打开 `https://github.com/Liuky1228/industry-chain-agent`
2. 点右上角绿色按钮 **「Code」→「Download ZIP」**。
3. 下载完成后：
   - 用 **Safari** 下载会自动解压；用 Chrome 需双击 `.zip` 解压。
   - 解压出来的文件夹通常叫 **`industry-chain-agent-main`**（注意带 `-main` 后缀）。
   - ✅ 建议把它拖到「桌面」或「下载」里，方便找。后面命令里的文件夹名就用你实际的名字（若叫 `industry-chain-agent-main` 就写这个）。

### 方式 B（命令行，装了 Git 才用）
```bash
git clone https://github.com/Liuky1228/industry-chain-agent.git
```
> ⚠️ 国内连 GitHub 常连不上 → 见文末「排错」用代理或改用方式 A 的 ZIP。

---

## 第 2 步：准备后端（Python 依赖，只做一次）

在终端里，进入你解压出来的项目文件夹（把路径换成你实际的；下面以桌面为例）：
```bash
cd ~/Desktop/industry-chain-agent-main
```
> 不确定文件夹叫什么？在终端输入 `ls ~/Desktop` 看一眼桌面上真实的文件夹名，抄进去。

然后**一行一行**执行：
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
- 如果 `pip` 报 `externally-managed-environment` 错误 → 说明你用了系统自带的 python3。**解决**：确认上面用的是 `python3 -m venv` 建了 `.venv` 并 `source` 激活（激活后命令行最前面会多 `(.venv)`），在 `(.venv)` 状态下再 `pip install` 就不会报这个错。若仍报错，重装 python.org 的 Python。
- 如果 `pip install` 很慢或卡住，换国内镜像：
  ```bash
  pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  ```
- 装完后命令行**最前面出现 `(.venv)`** 字样 → 说明进入虚拟环境成功。**之后启动后端都要保持这个状态**（即每次新开终端都要先 `cd` 进项目再 `source .venv/bin/activate`）。

---

## 第 3 步：准备前端（Node 依赖，网站需要，只做一次）

在「第 2 步那个已激活 `(.venv)` 的终端」里继续输入：
```bash
cd frontend
npm install
```
- 这步会下载前端零件，需要等 **1～3 分钟**（可能刷一堆警告，正常）。
- 完成后 `cd ..` 回到项目根目录。
- 如果 `npm install` 报权限错（EACCES），不要加 `sudo` 硬来；通常是之前用 `sudo` 装过 Node 导致。最省事：重装一次 Node（第 0.3 步的 `.pkg` 方式）即可。

---

## 第 4 步：填入你自己的 API 密钥

> Mac 上**强烈建议用终端创建/编辑 `.env`**，能 100% 避开 Windows 那种「存成 `.env.txt`」的坑。

1. 确保你在**项目根目录**且已激活 `(.venv)`（看命令行前面有没有 `(.venv)`）。
2. 复制模板并创建 `.env`：
   ```bash
   cp .env.example .env
   ```
3. 用系统自带的文本编辑器打开它：
   ```bash
   open -e .env
   ```
   （会弹出「文本编辑」程序；`.env` 名字已正确，不会变成 `.env.txt`。）
4. 找到这一行：
   ```
   DEEPSEEK_API_KEY=sk-请在此填写你自己的密钥
   ```
   把等号后面换成你自己申请的 `sk-` 密钥：
   ```
   DEEPSEEK_API_KEY=sk-你自己的密钥
   ```
5. `⌘ + S` 保存，关掉文本编辑窗口。其余内容**不要动**。

### 💡 关于"API 密钥"的几个关键要点（务必看）
- **变量名虽然叫 `DEEPSEEK_API_KEY`，但默认其实用的是「阿里云百炼」的 Qwen 模型。** 看 `.env` 另外两行：
  ```
  DEEPSEEK_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
  DEEPSEEK_MODEL=qwen3.7-plus
  ```
  即：**`.env` 默认已配好百炼地址和 Qwen 模型。你只去阿里云百炼申请一个 key 填进 `DEEPSEEK_API_KEY` 就能直接用**——最省事。
- **如果你手里是 DeepSeek / OpenAI / 硅基流动 / Moonshot 等别的「OpenAI 兼容」厂商的 key，也能用**，但要同时改 `.env` 这三行：
  ```
  DEEPSEEK_API_KEY=你的那家key
  DEEPSEEK_BASE_URL=那家的 OpenAI 兼容地址   # 例如 DeepSeek 是 https://api.deepseek.com/v1
  DEEPSEEK_MODEL=那家的模型名                # 例如 deepseek-chat
  ```
- ⚠️ **Anthropic / Claude 原生直接用不了**（协议不兼容）。非要用 Claude 得套 OpenAI 兼容网关（如 OpenRouter / LiteLLM）中转，新手不建议折腾。
- ⚠️ **必须用你自己的 key，不能抄作者的**。
- 改完 `.env` 后，要**重启后端**（关掉后端窗口再重跑第 5 步）才会生效。

---

## 第 5 步：启动（需要开两个终端窗口）

要同时跑"后端"和"前端"，所以开**两个**终端窗口（再开一个「终端」即可，两个窗口互不干扰）。

### 窗口 1：启动后端（8004）
在**激活了 `(.venv)` 的终端**里（如果关了就重新 `cd` 进项目根目录并 `source .venv/bin/activate`）：
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8004
```
- 如果提示 `uvicorn: command not found`，换成：
  ```bash
  python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8004
  ```
- 首次启动 macOS 可能弹「"python3" 想要接受传入网络连接」→ 点 **允许**。
- 启动成功后会一直刷日志（出现 `Uvicorn running on http://0.0.0.0:8004`）。**这个窗口不要关**。
- 验证：浏览器打开 `http://localhost:8004/api/health`，看到 `{"status":"ok",...}` 就说明后端活了。

### 窗口 2：启动前端（3004，网站）
新开一个终端窗口，进入前端目录（路径按你实际文件夹名改）：
```bash
cd ~/Desktop/industry-chain-agent-main/frontend
npm run dev
```
- 出现 `Local: http://localhost:3004/` 之类字样 → 前端活了。**这个窗口也不要关**。

---

## 第 6 步：打开网站，体验功能

1. 浏览器（Safari / Chrome）打开 **`http://localhost:3004`** → 网站出来了（和作者演示的一模一样）。
2. 在网站里**发起一个任务**（输入产业名，如"光伏""锂电池""半导体"）。
3. 看进度条 / 状态变化 → 任务完成后在**历史记录**里**下载 Word 报告**（`.docx`）。
4. 报告实体文件也落在你电脑的项目目录里：
   `industry-chain-agent-main/data/reports/产业名_产业链分析报告_时间戳.docx`，可直接用 Word/WPS 打开。

> **备用方案（不装 Node 也能出报告）**：只要后端（窗口 1）起来了，浏览器开 `http://localhost:8004/docs` → 找到 `POST /api/tasks` 点 Try it out → 填 `{"industry_name":"光伏"}` → Execute 拿到 `id` → `GET /api/tasks/{id}` 看进度 → 完成后 `GET /api/tasks/{id}/report` 直接下载 Word。这就是没有网站时的纯接口用法。

---

## 第 7 步：用完怎么关

- 窗口 1（后端）：点一下窗口，按 `Ctrl + C`
- 窗口 2（前端）：点一下窗口，按 `Ctrl + C`
- 下次想再用，重复**第 5 步**启动即可（第 2、3、4 步只需做一次）。

---

## 排错速查表（Mac 专属）

| 现象 | 处理 |
|---|---|
| `command not found: python3` | 没装 Python → 回第 0.3 步从 python.org 装 `.pkg` |
| `command not found: node` / `npm` | 没装 Node.js → 回第 0.3 步装（≥18） |
| `externally-managed-environment` 错误 | 你用了系统 python3。务必先 `python3 -m venv .venv` 再 `source .venv/bin/activate`，在 `(.venv)` 状态下 `pip install` |
| `pip install` 慢/超时 | 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `uvicorn: command not found` | 改用 `python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8004` |
| `npm install` 报 EACCES 权限错 | 别用 `sudo`。重装一次 Node（`.pkg` 方式）最省事 |
| `git clone` 失败 / 连不上 GitHub | 国内墙：① 改用「网页下载 ZIP」（第 1 步方式 A）；② 或挂代理后 `git clone` |
| 网站 `localhost:3004` 打不开 | 前端没起或没装依赖：回第 3 步 `npm install` 再第 5 步 `npm run dev`；确认窗口 2 出现 `Local: http://localhost:3004/` |
| 后端 `localhost:8004` 打不开 | 后端没起或依赖没装：回第 2 步；确认窗口 1 刷日志且无报错 |
| 端口 8004 / 3004 被占用 | 查占用：`lsof -i :8004` 或 `lsof -i :3004`，看最左列 PID；杀掉：`kill -9 <PID>`（把 `<PID>` 换成数字）；再重启 |
| 任务一直 `failed` / 报错含"配额""unauthorized" | `.env` 里的密钥无效或没余额 → 换你自己的有效 Key（第 4 步），并重启后端 |
| 网站能打开但发任务没反应 | 后端没起或 8004 不对；确认窗口 1 日志正常、且 `http://localhost:8004/api/health` 返回 ok |
| `.env` 改了不生效 | 改完 `.env` 必须**重启后端**（关窗口 1 再重跑第 5 步） |

---

## 一句话总结给使用者（Mac）
装好 **Python + Node**（建议 python.org / nodejs.org 的 `.pkg`）→ 下载项目（ZIP 或 git）→ 建虚拟环境 `python3 -m venv .venv` 并 `source` 激活、装后端依赖、前端 `npm install` → 用 `cp .env.example .env` + `open -e .env` 在 `.env` 填**你自己的** `sk-` 密钥 → 两个窗口分别跑后端(`uvicorn … 8004`)和前端(`npm run dev` → 3004) → 浏览器开 `localhost:3004` 用网站。报告是一份生成在你自己 Mac 上的 Word 文档。
