# 迁移到 Mac 指南（从 Windows 继续改进并推送 GitHub）

> 适用场景：你现在的项目在 **Windows** 上，想换到一台 **Mac** 上继续写代码、改功能，并且把改动推送回同一个 GitHub 仓库（`Liuky1228/industry-chain-agent`）。
> 阅读对象：零基础 / 没怎么用过命令行的同学。每一步都给了可直接粘贴的命令。

---

## 〇、先搞清楚：你 Windows 电脑上到底有几份相关文件夹

| 文件夹（Windows 路径） | 它是什么 | 迁移时要不要搬 | 说明 |
|---|---|---|---|
| `桌面/industry-chain-agent-dist` | **GitHub 仓库本体**，里面带 `.git`，远程已指向 `Liuky1228/industry-chain-agent` | **核心，必带（或 clone）** | 你 `git push` 的就是它 |
| `桌面/industry-report-agent` | 你**本地编辑用的源文件夹** | 可选 | 之前流程是"改源 → 复制到 dist"。到 Mac 可简化掉（见第六节） |
| `C:\Users\kingdee\.workbuddy\skills\industry-chain-agent` | **Skill 包**（SKILL.md + scripts/） | 仅当你要在 Mac 继续改 Skill 脚本 | 它不在 GitHub 里 |
| `桌面/industry-report-agent-skill.zip` | Skill 打包文件（v1.2.0） | 不需要 | SkillHub 上已有，Mac 可直接重下 |
| 本地的 `.env`、`data/`、`node_modules/`、`.venv/` | 密钥、生成的数据、依赖 | **都不搬** | 都被 `.gitignore` 忽略，到 Mac 重建 / 重装 |

### 最关键的事实
你 GitHub 上的仓库**目前是最新的**（已经把 `HomePage.jsx`、`README.md` 等全部推送上去了）。也就是说：**所有要公开的内容都已经在 GitHub 上**。所以到 Mac 上最干净的做法是「直接 `git clone`」，根本不用从 Windows 传任何文件。

---

## 一、推荐方法：在 Mac 上直接 `git clone`（无需传文件）

### 第 1 步：在 Mac 上装运行环境（只做一次）

打开 Mac 的「终端」（启动台里搜"终端"，或访达 → 应用程序 → 实用工具 → 终端），逐条执行下面命令来**检查**是否已安装：

```bash
git --version
python3 --version
node -v
npm -v
```

- 如果都正常显示版本号（git 任意版本、Python ≥ 3.10、Node ≥ 18）→ 跳到第 2 步。
- 如果某个命令报 `command not found`（找不到命令），按下面装：

**(a) git**：终端执行 `xcode-select --install`，弹窗点"安装"，装完重开终端再 `git --version` 验证。

**(b) Python（≥3.10）**：
- ⚠️ 不要用 Mac 系统自带的那个 `python3`（经常是 3.9，且装包装不进去）。
- 去 https://www.python.org/downloads/mac-osx/ 下载 **macOS 64-bit universal2 installer**（.pkg 文件），双击安装，**一路下一步**即可。装完 `python3 --version` 应显示 3.10+。

**(c) Node.js（≥18，会顺带装好 npm）**：
- 去 https://nodejs.org 下载 **LTS** 版 .pkg，双击安装。
- 或者装了 Homebrew 后执行 `brew install node`。
- 装完 `node -v`、`npm -v` 验证。

> 可选但推荐：装 Homebrew（Mac 的软件包管理器）
> ```bash
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```

---

### 第 2 步：配置 GitHub 身份认证（二选一，推荐「方案 A」）

GitHub 现在不允许用账号密码直接 push，必须用「令牌」或「SSH 密钥」。两种都行：

#### 方案 A：HTTPS + 个人访问令牌（最省心，不用管 SSH）

1. 浏览器登录 github.com → 右上角**头像** → **Settings**。
2. 左侧最底下 **Developer settings** → **Personal access tokens** → **Tokens (classic)**。
3. 点 **Generate new token (classic)**。
4. Note 随便填（如 `mac-laptop`）；Expiration 选 `No expiration` 或一个有期限的（如 90 天）。
5. 勾选 **`repo`** 这个权限框（最重要，给读写仓库的权限）。
6. 拉到底点 **Generate token**。
7. **复制**生成的那串 `ghp_xxxxxxxx` 令牌（只显示这一次，务必存好）。

然后在 Mac 终端 clone（用户名填 GitHub 账号，密码处**粘贴刚才的令牌**，终端不显示输入内容属正常）：

```bash
cd ~/Desktop
git clone https://github.com/Liuky1228/industry-chain-agent.git
```

#### 方案 B：SSH 密钥（一次配置，之后免密推送）

```bash
ssh-keygen -t ed25519 -C "你的邮箱地址"     # 一路回车，不要设密码短语也行
cat ~/.ssh/id_ed25519.pub                   # 终端会打印一长串，全选复制
```
1. 回到 github.com → 头像 → **Settings** → **SSH and GPG keys** → **New SSH key**。
2. Title 随便填（如 `mac-laptop`），Key 框粘贴刚才复制的那串公钥。
3. 点 **Add SSH key**。

然后 clone（注意地址是 `git@` 开头）：

```bash
cd ~/Desktop
git clone git@github.com:Liuky1228/industry-chain-agent.git
```

> ⚠️ **重要差异**：你 Windows 上的 `.gitconfig` 里有一条规则，会把 `https://github.com/` 自动改成 SSH 地址。这条规则**不会**跟着到 Mac。所以在 Mac 上：
> - 用方案 A 就老老实实写 `https://...` 地址 + 令牌；
> - 用方案 B 就直接写 `git@github.com:...` 地址。
> 别指望 Mac 会自动帮你改地址。

---

### 第 3 步：clone 完成后验证

```bash
cd ~/Desktop/industry-chain-agent
git log --oneline -5
```
应能看到你之前的提交记录（含 `docs: 重写 README...`、`更新前端首页 HomePage 组件`、`Initial commit...`）。能看到就说明代码完整拉下来了。

---

### 第 4 步：安装依赖（只做一次）

后端（Python）：
```bash
cd ~/Desktop/industry-chain-agent
python3 -m venv .venv
source .venv/bin/activate          # 激活后，终端提示符前面会出现 (.venv)
pip install --upgrade pip
pip install -r requirements.txt
```
> 国内装 pip 慢，可加清华镜像：
> `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

前端（Node）：
```bash
cd ~/Desktop/industry-chain-agent/frontend
npm install
```
> npm 慢可切换国内镜像：`npm config set registry https://registry.npmmirror.com` 然后再 `npm install`。

回到项目根目录：
```bash
cd ~/Desktop/industry-chain-agent
```

---

### 第 5 步：重建 `.env`（密钥不传，自己建）

`.env` 里存的是你的 API Key，被 `.gitignore` 忽略，**不会**从 GitHub 下来，所以 Mac 上要自己建一个：

```bash
cp .env.example .env
open -e .env
```
`open -e` 会用"文本编辑"打开。把这一行改掉：
```
DEEPSEEK_API_KEY=sk-请在此填写你自己的密钥
```
改成你自己的真实 key（例如阿里云百炼申请的 `sk-` 开头那串）。**注意变量名虽叫 DEEPSEEK，但默认 `.env` 里 `DEEPSEEK_BASE_URL` 指向阿里云百炼、`DEEPSEEK_MODEL=qwen3.7-plus`，所以填百炼的 key 直接能用。** 改完 `⌘+S` 保存，关掉窗口。

> 避坑：文件名必须是 `.env`，不要存成 `.env.txt`。用 `open -e` 打开的是隐藏文件，文本编辑可能会想给你加 `.txt` 后缀——保存时如果弹"纯文本"提示，选"使用 .env 扩展名"。

---

### 第 6 步：跑起来验证

需要**开两个终端窗口**：

**窗口 1（后端）**——确认还在 `(.venv)` 激活状态：
```bash
cd ~/Desktop/industry-chain-agent
source .venv/bin/activate        # 如果刚才关了终端，重新激活
uvicorn app.main:app --host 0.0.0.0 --port 8004
```
看到 `Uvicorn running on http://0.0.0.0:8004` 就成功了。

**窗口 2（前端）**：
```bash
cd ~/Desktop/industry-chain-agent/frontend
npm run dev
```
看到 `Local: http://localhost:3004` 就成功了。

浏览器打开 **http://localhost:3004** → 输入一个产业名（如"半导体"）→ 能生成报告即迁移成功。

> 如果 Mac 弹出"是否允许传入网络连接"，点**允许**。
> 端口被占用：用 `lsof -i :8004` 找到进程 PID，再 `kill -9 <PID>` 杀掉重来。

---

### 第 7 步：以后在 Mac 上改进并推回 GitHub

```bash
cd ~/Desktop/industry-chain-agent
git add -A                          # 暂存所有改动
git commit -m "在 Mac 上改了 XX 功能"   # 写清楚改了啥
git push                            # 推送到 GitHub
```
就这三步。GitHub 是同一个仓库，历史全在，Windows 上原来的那份会变成"旧副本"（见第七节）。

---

## 二、备选方法：物理搬运文件夹（U 盘 / 云盘 / 微信文件传输助手）

如果你**不想**走 clone（比如 Mac 暂时没网、或想完整带走本地历史），就直接搬 `industry-chain-agent-dist` 整个文件夹。

### 打包（在 Windows 上）
1. 进入 `桌面/industry-chain-agent-dist`。
2. **整个文件夹压缩**，重点是：**一定要带上里面的 `.git` 文件夹**（否则 git 历史丢失，等于变成普通文件夹，没法增量 push）。
3. 建议排除这些大文件/敏感文件再打包：
   - `frontend/node_modules/`（巨大，到 Mac 重装）
   - `data/`、`*.db`（生成的报告数据，可重建）
   - `.env`（即便在里面也没真实 key，因为 config 默认是空，但别传更安心）
4. 把压缩包传到 Mac（U 盘拷贝 / 百度网盘 / 微信文件传输助手等）。

### 在 Mac 上还原并使用
1. 解压到 `~/Desktop/industry-chain-agent-dist`。
2. 仍要走「方法一 第 2 步」**配置 GitHub 认证**——因为你的 SSH 密钥在 Windows，Mac 上没有，不配就无法 `git push`。
3. 然后走「方法一 第 4、5、6 步」装依赖、建 `.env`、跑起来。

> 比较：物理搬运要带 `.git`、要手挑排除大文件、还得重新配认证；`git clone` 一步到位。**所以默认用方法一。**

---

## 三、如果你还要在 Mac 上继续改 Skill 本身

Skill 包（SKILL.md + scripts/）**不在 GitHub 里**，要单独处理：

- **方式 1（推荐）**：Mac 上装了 WorkBuddy 后，从 SkillHub 重新"安装"这个 Skill，它会在 `~/.workbuddy/skills/industry-chain-agent` 重新生成脚本（拿到当前 v1.2.0）。之后你直接在 Mac 上改这些脚本即可。
- **方式 2**：把 Windows 上的 `C:\Users\kingdee\.workbuddy\skills\industry-chain-agent` 整个文件夹，拷到 Mac 的同名路径 `~/.workbuddy/skills/industry-chain-agent`（Mac 路径以 WorkBuddy 实际为准）。

改完 Skill 脚本后若想发布：重新打成 zip，去 SkillHub 覆盖上传同名 skill（**只有改了 Skill 自己的脚本才需要这步，纯项目代码更新不用**）。

---

## 四、重点坑清单（必读）

1. **SSH 密钥不跟随**：Windows 上能免密 push 是因为有 SSH key，Mac 上没有。必须按「第 2 步」重新配（新生成 key 加进 GitHub，或复制 Windows 的私钥到 Mac——后者不太安全，推荐前者）。
2. **`.gitconfig` 的 insteadOf 规则不跟随**：Windows 把 `https://` 自动改 SSH 的规则不会到 Mac，Mac 上按实际地址 clone 即可。
3. **`.env` 不传**：被 gitignore，GitHub 上没有，Mac 上 `cp .env.example .env` 自己填 key。
4. **依赖不传**：`node_modules/`、`.venv/` 都被 gitignore，Mac 上 `npm install` + `pip install` 重装。
5. **生成数据不传**：`data/`、`*.db` 是运行产物，重跑会再生，一般不用搬。
6. **真实 API Key 永远别进仓库**：`config.py` 默认值已经是 `""`，不要在 Mac 上又把 key 写死回去。

---

## 五、给 Mac 上"简化工作流"的建议

Windows 上你维护了两个文件夹（源 `industry-report-agent` + 仓库 `industry-chain-agent-dist`），到 Mac **建议只保留 clone 出来的那一个仓库**，直接在里面编辑 → `commit` → `push`，不必再"改源再复制进 dist"。这样以后更新 GitHub 只要一条 `git push`，最不容易出错。

```
以前（Windows）：  改 industry-report-agent  →  复制到  industry-chain-agent-dist  →  push
推荐（Mac）：      直接在 industry-chain-agent 里改  →  push
```

---

## 六、双向同步提醒

你现在是"从 Windows 迁到 Mac"，Windows 那份会变成**旧副本**。如果将来某天又回到 Windows 改东西：
- 先在 Windows 的 `industry-chain-agent-dist` 里 `git pull` 把 Mac 的改动拉下来，再继续改；
- 否则两边会分叉、push 时冲突。

---

## 七、迁移成功验证清单（做完对照打勾）

- [ ] Mac 终端能跑 `git --version` / `python3 --version` / `node -v` / `npm -v`
- [ ] `git clone` 成功，`git log` 能看到之前的提交
- [ ] `pip install -r requirements.txt` 无报错
- [ ] `frontend/npm install` 无报错
- [ ] `.env` 已建好且填了真实 key
- [ ] 后端 `http://localhost:8004/docs` 能打开
- [ ] 前端 `http://localhost:3004` 能打开并生成报告
- [ ] `git push` 能成功（第一次可能需要按第 2 步配好认证）
- [ ] 刷新 GitHub 仓库页面，能看到最新代码

---

## 八、排错速查表

| 现象 | 可能原因 | 解决 |
|---|---|---|
| `command not found: git/python3/node` | 没装 | 按第 1 步安装 |
| `git clone` 要密码但令牌不对 / 403 | 用了账号密码而非令牌；或 token 没 `repo` 权限 | 改用令牌；去 GitHub 重新生成带 `repo` 的 token |
| `Permission denied (publickey)` | SSH key 没配 / 没加进 GitHub | 走第 2 步方案 B，把公钥加到 GitHub |
| `externally-managed-environment` | 往系统 Python 装包 | 我们已经用 `python3 -m venv .venv` 隔离了，确认激活了 `(.venv)` 再装 |
| `pip install` 极慢 / 超时 | 网络 | 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `npm install` 极慢 | 网络 | `npm config set registry https://registry.npmmirror.com` |
| 前端打不开 / 端口被占 | 8004 或 3004 被占用 | `lsof -i :8004` / `lsof -i :3004` 找到 PID，`kill -9 <PID>` |
| `git push` 报 `non-fast-forward` | 本地落后远程 | 先 `git pull` 再 `git push` |
| `.env` 不生效 | 存成了 `.env.txt` | 用 `ls -la` 看文件名，改名回 `.env` |

---

完成以上步骤，你的项目就完整迁移到 Mac 并可以继续改进、推送 GitHub 了。
