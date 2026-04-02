# clawshire-open-skill

虾饵（ClawShire）A 股上市公司公告数据查询技能集，专为 Claude AI 设计。

## 技能列表

| 技能 | 说明 | 数据范围 |
| --- | --- | --- |
| `clawshire-data-query` | 公告提取结果查询 | A 股全市场（沪深北） |
| `clawshire-annual-report` | 年报结构化数据查询（含 CSV/Excel 导出） | 北交所上市公司 |
| `clawshire-financial-analysis` | 年报 PDF 财务风险分析（25+ 条规则） | 通用（任意上市公司） |
| `clawshire-doc-extract-engine` | 通用 PDF 提取（Schema 对话 + 提取 + 迭代修正） | 用户自备 PDF（需平台开启文档提取插件） |

## 快速开始

### 1. 安装技能

在 Claude AI 中安装本技能集：

```bash
# 克隆仓库到本地
git clone https://github.com/lihanghang/clawshire-open-skill.git

# 在 Claude 配置中添加技能路径
# 或通过 Claude 插件市场安装
```

### 2. 配置 API Key

登录 [ClawShire 控制台](https://clawshire.cn)，认证后手动创建 API Key，然后设置环境变量：

```bash
export CLAWSHIRE_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 3. 在 Agent 中使用

安装后，直接在 Claude 对话中使用：

**查询今日公告：**
```
帮我查询今天的上市公司公告
```

**按证券代码查询：**
```
查询平安银行（000001）最近的董事会决议公告
```

**查询北交所年报：**
```
查询九典制药（833359）的 2024 年报数据
```

**年报财务风险分析：**
```
分析这份年报 PDF 的财务风险：/path/to/年报.pdf
```

**通用文档提取：**
```
帮我提取这份合同的关键信息：/path/to/合同.pdf
需要提取：标题、签署日期、金额、甲乙方
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
│   ├── clawshire-financial-analysis/       # 财务风险分析技能
│   │   ├── SKILL.md                        # 技能描述与工作流
│   │   └── scripts/
│   │       └── financial_analysis_client.py # 财务风险分析 CLI
│   └── clawshire-doc-extract-engine/       # 通用 PDF 文档提取技能
│       ├── SKILL.md
│       ├── scripts/
│       │   └── clawshire_doc_extract_client.py
│       └── evals/
│           └── evals.json
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
