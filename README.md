# 产业链分析 Agent

输入产业名称，AI 自动爬取公开研报、提取企业主营业务与商业关系、构建产业链上中下游图谱，并生成专业的 Word 格式产业链报告。

## 技术架构

- **后端**: FastAPI + SQLAlchemy + SQLite
- **前端**: React + Vite + ECharts
- **LLM**: DeepSeek API（兼容 OpenAI 格式，1M 上下文窗口）
- **数据源**: 东方财富研报 API + 巨潮资讯公告 API
- **PDF 解析**: pdfplumber + pymupdf

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（前端开发用）
- DeepSeek API Key（[申请地址](https://platform.deepseek.com/)）

### 一键启动（Windows）

```bash
start.bat
```

### 手动启动

**1. 后端**

```bash
# 创建虚拟环境
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Mac/Linux

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 DeepSeek API Key

# 启动后端
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端启动后访问 http://localhost:8000/docs 可查看 API 文档。

**2. 前端**

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端访问 http://localhost:3000

### 构建前端（生产部署）

```bash
cd frontend
npm run build
# 构建产物在 frontend/dist/ 目录
```

## 项目结构

```
industry-chain-agent/
├── app/                          # 后端主代码
│   ├── main.py                   # FastAPI 入口 + 后台任务管道
│   ├── config.py                 # 配置管理
│   ├── database.py               # 数据库初始化
│   ├── database_models.py        # ORM 模型
│   ├── api_models.py             # API 请求/响应模型
│   ├── crawler/                  # 研报爬虫模块
│   │   ├── eastmoney.py          # 东方财富研报 API
│   │   ├── cninfo.py             # 巨潮资讯公告 API
│   │   ├── keyword_expander.py   # LLM 关键词扩展
│   │   └── pipeline.py           # 爬虫编排管道
│   ├── parser/                   # PDF 解析模块
│   │   └── pdf_parser.py         # PDF 文本/表格提取
│   ├── analyzer/                 # LLM 分析模块
│   │   ├── extractor.py          # 信息提取（两轮 Prompt）
│   │   └── chain_builder.py      # 产业链图谱构建
│   └── generator/                # 报告生成模块
│       └── docx_generator.py     # Word 文档生成
├── frontend/                     # React 前端
│   ├── src/
│   │   ├── App.jsx               # 路由入口
│   │   ├── components/
│   │   │   ├── HomePage.jsx      # 首页（输入+历史）
│   │   │   ├── ResultPage.jsx    # 结果展示页
│   │   │   └── ChainGraph.jsx    # ECharts 产业链图谱
│   │   └── services/
│   │       └── api.js            # API 请求封装
│   └── vite.config.js            # Vite 配置（含代理）
├── data/                         # 运行时数据
│   ├── pdfs/                     # 下载的研报 PDF
│   └── reports/                  # 生成的分析报告
├── requirements.txt
├── .env.example
├── start.bat                     # Windows 启动脚本
├── start.sh                      # Linux/Mac 启动脚本
└── README.md
```

## 核心流程

```
用户输入产业名称
    ↓
LLM 扩展子领域关键词
    ↓
东方财富 API 搜索行业研报 + 个股研报
    ↓
下载 PDF 文件
    ↓
pdfplumber 提取文本和表格
    ↓
DeepSeek 第一轮：逐份研报提取公司信息、上下游关系
    ↓
DeepSeek 第二轮：跨研报整合、产业链层级分析
    ↓
networkx 构建产业链有向图 + 间接关系推断
    ↓
python-docx 生成结构化 Word 报告
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tasks` | 创建分析任务 |
| GET | `/api/tasks` | 任务列表 |
| GET | `/api/tasks/{id}` | 任务详情（含可视化数据） |
| GET | `/api/tasks/{id}/stream` | SSE 实时进度推送 |
| GET | `/api/tasks/{id}/report` | 下载 Word 报告 |
| DELETE | `/api/tasks/{id}` | 删除任务 |
| GET | `/api/health` | 健康检查 |

## 配置说明

编辑 `.env` 文件：

```env
# DeepSeek API（必填）
DEEPSEEK_API_KEY=your-api-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 爬虫参数
CRAWL_DELAY_SECONDS=3          # 请求间隔（秒）
MAX_REPORTS_PER_TASK=30        # 每次任务最大研报数
REPORT_DATE_RANGE_DAYS=180     # 研报时间范围（天）
```

## 成本估算

以分析一个产业链为例（30 份研报，每份约 2 万字）：

- LLM 调用成本：约 **¥1 以内**（DeepSeek V4 Flash 价格极低）
- 数据爬取：无直接成本（公开 API）
- 总耗时：约 5-15 分钟（取决于研报数量和网络速度）

## 注意事项

- 研报版权归原作者和券商所有，本工具仅供个人研究使用
- 东方财富 API 参数可能不定期变动，如遇爬取失败请检查接口是否有更新
- LLM 提取结果可能存在误差，建议结合人工审核
- 首次运行会自动创建 SQLite 数据库（`data/industry_chain.db`）
