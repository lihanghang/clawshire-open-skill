# clawshire-open-skill

虾饵（ClawShire）A 股上市公司公告数据查询技能集，专为 Claude AI 设计。

## 技能列表

| 技能 | 说明 | 数据范围 |
| --- | --- | --- |
| `clawshire-data-query` | 公告提取结果查询 | A 股全市场（沪深北） |
| `clawshire-annual-report` | 年报结构化数据查询（含 CSV/Excel 导出） | 北交所上市公司 |
| `clawshire-financial-analysis` | 年报 PDF 财务风险分析（25+ 条规则） | 通用（任意上市公司） |

## 快速开始

### 1. 获取 API Key

登录 [ClawShire 控制台](https://clawshire.cn)，认证后手动创建 API Key，然后设置环境变量：

```bash
export CLAWSHIRE_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 2. 查询今日公告

```bash
python skills/clawshire-data-query/scripts/clawshire_client.py announcements
```

### 3. 按证券代码查询公告

```bash
python skills/clawshire-data-query/scripts/clawshire_client.py stock 000001 \
  --start-date 2026-03-01 --end-date 2026-03-10 --infotype 董事会决议
```

### 4. 按公告链接查询

```bash
python skills/clawshire-data-query/scripts/clawshire_client.py met-link \
  "http://www.szse.cn/api/disc/info/query?id=123abc"
```

### 5. 查询北交所年报

```bash
# 按证券代码查询年报
python skills/clawshire-annual-report/scripts/clawshire_annual_client.py stock 833359

# 查询全市场 2024 年报
python skills/clawshire-annual-report/scripts/clawshire_annual_client.py list --year 2024

# 导出为 Excel
python skills/clawshire-annual-report/scripts/clawshire_annual_client.py list --year 2024 --output excel
```

### 6. 年报财务风险分析

```bash
# 终端输出风险摘要
python skills/clawshire-financial-analysis/scripts/financial_analysis_client.py analyze path/to/年报.pdf

# 导出 HTML 报告（自动保存到 PDF 同目录）
python skills/clawshire-financial-analysis/scripts/financial_analysis_client.py analyze path/to/年报.pdf --output html

# 查看所有分析规则
python skills/clawshire-financial-analysis/scripts/financial_analysis_client.py rules
```

## 项目结构

```text
clawshire-open-skill/
├── .claude-plugin/
│   └── marketplace.json                    # Claude 插件市场配置
├── skills/
│   ├── clawshire-data-query/               # A 股公告查询技能
│   │   ├── SKILL.md                        # 技能描述与工作流
│   │   ├── scripts/
│   │   │   └── clawshire_client.py         # Python CLI 客户端
│   │   └── evals/
│   │       └── evals.json                  # 评测用例
│   ├── clawshire-annual-report/            # 北交所年报技能
│   │   ├── SKILL.md                        # 技能描述与工作流
│   │   └── scripts/
│   │       └── clawshire_annual_client.py  # 年报查询 CLI（支持 CSV/Excel 导出）
│   └── clawshire-financial-analysis/       # 财务风险分析技能
│       ├── SKILL.md                        # 技能描述与工作流
│       └── scripts/
│           └── financial_analysis_client.py# 财务风险分析 CLI
└── README.md
```

## 技术支持

- 官网：[clawshire.cn](https://clawshire.cn)
- API 文档：[clawshire.cn/api-docs](https://clawshire.cn/api-docs)

## 更新技能

如需更新到最新版本：

```bash
# 方式 1：如果你使用 git clone 的本地仓库
cd <clone 目录>
git pull

# 方式 2：如果你通过 npx 安装
npx <package-name> update

# 或重新安装
npm uninstall <package-name> -g
npx <package-name>
```

> 建议关注 [GitHub Releases](https://github.com/lihanghang/clawshire-open-skill/releases) 了解更新内容。
