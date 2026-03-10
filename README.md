# clawshire-open-skill

虾饵（ClawShire）A 股上市公司公告数据查询技能集。

支持按日期范围、证券代码、公告原文链接检索结构化提取结果。

## 快速开始

### 1. 获取 API Key

登录控制台 https://clawshire.cn，认证后手动创建 API Key，然后设置环境变量：

```bash
export CLAWSHIRE_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 2. 查询今日公告

```bash
python skills/clawshire-data-query/scripts/clawshire_client.py announcements
```

### 3. 按证券代码查询

```bash
python skills/clawshire-data-query/scripts/clawshire_client.py stock 000001 \
  --start-date 2026-03-01 --end-date 2026-03-10 --infotype 董事会决议
```

### 4. 按公告链接查询

```bash
python skills/clawshire-data-query/scripts/clawshire_client.py met-link \
  "http://www.szse.cn/api/disc/info/query?id=123abc"
```

## 项目结构

```
clawshire-open-skill/
├── .claude-plugin/
│   └── marketplace.json          # Claude 插件市场配置
├── skills/clawshire-data-query/
│   ├── SKILL.md                  # 技能描述与工作流
│   ├── scripts/
│   │   └── clawshire_client.py   # Python CLI 客户端
│   └── evals/
│       └── evals.json            # 评测用例
└── README.md
```

## 技术支持

- 官网：https://clawshire.cn
- API 文档：https://api.clawshire.cn/docs
