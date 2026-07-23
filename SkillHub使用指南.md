# 通过 SkillHub 使用「产业链分析 Agent」详细指南

> 适用对象：想在 WorkBuddy 里直接装这个 Skill、用它生成产业链分析报告的人（零基础也能照做）。  
> 这份指南讲的是「怎么用别人已经发布到 SkillHub 的这个 Skill」，不涉及改代码、不涉及 GitHub。

---

## 〇、先认识一下这个 Skill

**它能做什么**：输入一个产业名（如"半导体""新能源汽车"），它会自动抓取公开研报、用大模型抽取企业之间的上下游关系、构建产业链图谱，最后生成一份 **8 章、机构风格的 Word 报告**，还能在网页上查看。

**它怎么跑起来的**：

- 第一次使用时，Skill 会自动帮你**装好整套程序**（从 GitHub 拉代码、建 Python 环境、装依赖、装前端），不需要你手动敲一堆命令。
- 装好后，你只需要**填一个自己的 API Key**，就能让它开始干活。
- 它提供一个**本地网站** `http://localhost:3004`，在里面输入产业名、看任务进度、下载报告。

**你需要自己准备的 3 样东西**：

1. 一台装了 WorkBuddy 的电脑（Windows / macOS / Linux 都行）。
2. 一个**自己的大模型 API Key**（下面会讲去哪申请，必须用自己的，不能抄作者的）。
3. 电脑上装好 **Node.js ≥ 18**、**Python ≥ 3.10**、**git**（下面教怎么装/检查）。

---

## 一、安装前准备（必须满足，否则 Skill 跑不起来）

### 1.1 检查 / 安装 Node.js（≥ 18）

打开终端（Windows 用 PowerShell 或 CMD；Mac 用"终端"），输入：

```bash
node -v
```

- 显示 `v18.x.x` 或更高 → 已装，跳过。
- 显示"不是内部或外部命令"或版本低于 18 → 去 <https://nodejs.org> 下载 **LTS** 版，双击安装（会顺带装好 npm）。

> 为什么需要它：Skill 提供的网页界面（localhost:3004）是前端，需要 Node.js 才能启动。没装 Node 时，Skill 仍能出报告（只走后端接口），但**没有网页界面**。

### 1.2 检查 / 安装 Python（≥ 3.10）

```bash
python --version      # Windows
python3 --version     # macOS / Linux（Mac 通常要写 python3）
```

- 显示 3.10+ → 已装。
- 没装 → Windows 去 <https://www.python.org> 下载，安装时**务必勾选 "Add Python to PATH"**；Mac 去 python.org 下 .pkg（别用系统自带那个 python3，容易装不进包）。

### 1.3 检查 / 安装 git

```bash
git --version
```

- 显示版本号 → 已装。
- 没装 → Windows 去 <https://git-scm.com> 下载安装；Mac 执行 `xcode-select --install` 或装 Homebrew 后 `brew install git`。

### 1.4 准备你自己的 API Key

Skill 调用大模型需要 Key。默认配置指向**阿里云百炼的 Qwen** 模型，所以最省事的做法：

1. 打开 <https://bailian.console.aliyun.com/> ，用你自己的账号登录。
2. 开通模型服务，申请一个 `sk-` 开头的 API Key（具体入口叫"API-KEY 管理"或"模型服务"→"API 调用"）。
3. 复制这串 Key 备用。 

> 也可以用 DeepSeek、OpenAI 等**任何 OpenAI 兼容**的 Key，但要把 `.env` 里的 `DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL` 也一起改掉（见第四节）。  
> ❌ **Claude（Anthropic）原生不支持**，因为本项目只走 OpenAI 兼容协议。  
> 🔑 必须用自己的 Key，不要抄作者的——作者的 Key 已经撤掉/不能外泄。

---

## 二、从 SkillHub 安装这个 Skill

### 2.1 打开 WorkBuddy

启动 WorkBuddy（桌面客户端或对应入口），登录你的账号。

### 2.2 进入技能市场（SkillHub）

在 WorkBuddy 里找到「技能中心 / 插件市场 / SkillHub」（不同版本叫法略有差异，一般在左侧边栏或设置里，标有"专家""技能""市场"之类的入口）。

### 2.3 搜索并安装

- 在搜索框输入：`industry-chain-agent` 或 `产业链分析`。
- 找到名为 **industry-chain-agent** 的技能（作者 intern，分类"办公效率"）。
- 点 **安装 / 添加到我的技能**。

### 2.4 确认安装成功

安装完成后，在「我的技能」列表里能看到 **industry-chain-agent** 即成功。

> 💡 小提示：部分版本的 WorkBuddy 也支持**直接在对话里说**"帮我安装 industry-chain-agent 技能"，它会自动去市场拉取安装。如果界面找不到，可以试试这句话。

---

## 三、首次使用：让 Skill 自动帮你装好程序

装好 Skill 后，**第一次**在对话里对 WorkBuddy 说下面任意一句即可触发：

- "我想分析 半导体 产业链"
- "帮我做一份 新能源汽车 产业报告"
- "初始化 industry-chain-agent"

Skill 随后会运行它的安装脚本（`install.py`），自动做这些事（你不用管，等它跑完）：

1. 从 GitHub **克隆**项目代码到本机 `~/.industry-chain-agent`（Windows 在 `C:\Users\你的用户名\.industry-chain-agent`）。
2. 创建 Python 虚拟环境（`.venv`）。
3. `pip install` 安装后端依赖。
4. `npm install` 安装前端依赖（需要第 1.1 步的 Node.js）。
5. 生成一份 `.env` 配置文件。

⚠️ **它会在这里停一下，提示你"请编辑 .env 填入 DEEPSEEK_API_KEY"** —— 这是正常的，因为 Key 必须你自己填。继续看第四节。

> 说明：克隆只需一次。以后再调用 Skill，它会检测到程序已存在，跳过克隆直接干活。

---

## 四、填入你的 API Key（必须手动做，最关键的一步）

### 4.1 找到 `.env` 文件

克隆完成后，文件在本机这个位置：

- **Windows**：`C:\Users\你的用户名\.industry-chain-agent\.env`
- **macOS / Linux**：`~/.industry-chain-agent/.env`（即 `/Users/你的用户名/.industry-chain-agent/.env`）

### 4.2 用文本编辑器打开它

- **Windows**：右键 → 用"记事本"打开。**保存时务必确认文件名是 `.env`，不要被记事本存成 `.env.txt`**（保存对话框里"保存类型"选"所有文件"，文件名带英文引号 `.env"` 可强制）。
- **macOS**：终端执行 `open -e ~/.industry-chain-agent/.env`，或 `nano ~/.industry-chain-agent/.env`。
- **Linux**：`nano ~/.industry-chain-agent/.env`。

### 4.3 修改这一行

找到：

```
DEEPSEEK_API_KEY=sk-请在此填写你自己的密钥
```

把等号后面换成你自己的 Key：

```
DEEPSEEK_API_KEY=sk-你从百炼申请的真实key
```

> 如果用的是百炼 Qwen（默认），只改这一行就够了，其余 `BASE_URL`/`MODEL` 保持默认。  
> 如果用 DeepSeek / OpenAI 等其他 OpenAI 兼容 Key，要同时把 `DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL` 改成对应的值。

### 4.4 保存，然后重新对 WorkBuddy 说一次

保存文件后，回到 WorkBuddy 对话，再说一次"分析 XX 产业链"。这次 Skill 检测到 Key 已填，就会正式开始跑任务。

---

## 五、正式使用：让 Skill 出报告

### 5.1 怎么"叫"它（触发词）

在 WorkBuddy 对话里说下面任意一句：

- "分析 X 产业链" / "做 X 产业报告" / "跑 X 产业链" → 创建新任务
- "看下 X 任务" / 给它一个 `task_id` → 查询某个任务
- "最近的任务" / "历史记录" → 列出最近的任务

### 5.2 它会做什么

1. 创建任务，开始抓取公开研报、调用大模型抽取关系。
2. 自动轮询进度（你不用一直盯着），直到"完成 / 失败"。
3. 完成后告诉你：报告下载链接、企业数量、传导关系数量。

### 5.3 在哪里看结果

有两种方式：

- **网页界面（推荐）**：Skill 会启动网站，浏览器打开 **<http://localhost:3004>** ，在"任务历史"里能看到任务、点开下载 Word 报告。
- **直接下载**：报告链接形如 `http://localhost:8004/api/tasks/{task_id}/report` ，复制到浏览器即可下载。

### 5.4 网页打不开怎么办

- 网站由 Skill 的 `start_site.py` 同时启动前后端。如果没自动开，可让 WorkBuddy "启动网站"或"运行 start_site.py"。
- 确认浏览器地址是 `http://localhost:3004`（不是 https，也不要加端口外的路径）。
- Mac 首次可能弹"允许传入网络连接"，点允许。

---

## 六、常用操作速查

| 想做         | 对 WorkBuddy 说                |
| ---------- | ---------------------------- |
| 新建并跑一个产业分析 | "分析 半导体 产业链"                 |
| 看某个任务结果    | "查任务 \<task_id>"             |
| 列出最近任务     | "最近的任务"                      |
| 下载报告       | "下载任务 \<task_id> 的报告"        |
| 打开网页界面     | "启动网站" / "打开 localhost:3004" |
| 只出报告不要网页   | "只用后端 API 跑 X 产业链"           |

---

## 七、怎么获取作者的更新

这个 Skill 的项目代码放在 GitHub，Skill 第一次使用时 `git clone` 到了你本机 `~/.industry-chain-agent`。**作者更新 GitHub 后，你本地的这份不会自动变**。要拿到更新：

- **方法 1（最省心）**：关掉 Skill 相关程序，删掉 `~/.industry-chain-agent` 整个文件夹，再对 WorkBuddy 说一次"分析 XX 产业链"，Skill 会重新克隆最新版。
- **方法 2（轻量）**：终端里执行
  ```bash
  cd ~/.industry-chain-agent      # Windows 用对应的 C:\Users\用户名\.industry-chain-agent
  git pull
  ```
  然后重启 Skill 的服务即可。

> 注意：SkillHub 上那个 Skill 包本身（脚本）一般不用重装；需要更新的是它克隆下来的项目代码（上面两种方法解决）。

---

## 八、排错速查表

| 现象                                | 原因                              | 解决                                   |
| --------------------------------- | ------------------------------- | ------------------------------------ |
| Skill 提示"请填入 DEEPSEEK_API_KEY"后停下 | 没填 Key / 填错文件                   | 按第四节打开 `.env` 填 Key，重说一次指令           |
| 报"后端未启动 / 健康检查失败"                 | 后端没开                            | 让 Skill "启动网站"或"启动后端"，等约 12 秒再试      |
| 报"缺密钥（返回码 5）"                     | `.env` 里 Key 是空的或存成了 `.env.txt` | 确认 `.env` 文件名正确、Key 已填且保存            |
| 报"配额耗尽 429"                       | Key 额度用完了                       | 去申请 Key 的平台充值 / 换 Key，改 `.env` 后重启后端 |
| 报"端口被占用"                          | 8004 或 3004 被别的程序占了             | 关闭占用端口的程序，或让 Skill "停止网站"后重开         |
| 卡在 90%（整合阶段）                      | 已知问题                            | 看后端日志，取消后重试该任务                       |
| 网页打不开                             | 前端没起 / Node 没装                  | 确认装了 Node.js ≥18；让 Skill 重启网站        |
| `git clone` 失败                    | 没装 git / 网络连不上 GitHub           | 装 git；国内连 GitHub 不稳可多试几次或用代理         |

---

## 九、安全须知（放心用）

- 你的 API Key 只存在你本机的 `.env` 文件里，**不会**被写进对话，也**不会**被打包进 Skill 发布出去。
- 项目仓库已用 `.gitignore` 忽略 `.env`，Key 不会上传到 GitHub。
- 后端默认只监听本机 `localhost`，不会把服务暴露到公网。

---

照着上面九节做，你就能在 WorkBuddy 里通过 SkillHub 装上这个 Skill、填好自己的 Key、生成并下载产业链分析报告了。遇到卡住的地方，先看第八节的排错表。
