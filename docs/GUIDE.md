# Agent 记忆检索 · 项目搭建与跟做详解

> 项目仓库：https://github.com/Jxg516/fastapi-agent-memory
> 快速上手：见仓库根目录 [README.md](../README.md)

## 4.1 你将完成什么（验收标准）

一个单文件 FastAPI 服务，把 Agent 的「长期记忆」压到最小可用：

- 写入记忆：正文、标签、重要度（1-5）。
- 检索记忆：关键词命中数 × 重要度权重 × 时间衰减，返回带分数的 Top N。
- 命中后累加 `use_count`，为后续「常用记忆优先」留口子。

验收四条：

1. `GET /health` 返回 `{"status":"ok"}`。
2. `POST /memories` 返回 201 和完整记录。
3. `GET /memories/search?q=部署` 命中相关记录且分数降序。
4. 重复检索后 `use_count` 递增。

## 4.2 仓库里有什么（结构说明）

```text
fastapi-agent-memory/
├─ main.py            # 全部服务逻辑：模型、建表、打分、路由
├─ requirements.txt   # fastapi + uvicorn
├─ README.md          # 最短上手
├─ docs/GUIDE.md      # 本文件
└─ .gitignore         # 忽略 .venv / db / 缓存
```

刻意不拆 `routers/`、`services/`：这一版只有四个接口，拆层会让读者在文件间跳转，收益为零。等出现第二个存储后端或鉴权需求再拆。

## 4.3 接口与状态（跟做时对照表）

| 方法 | 路径 | 入参 | 出参 | 失败 |
|------|------|------|------|------|
| GET | `/health` | — | `status`、`db` | — |
| POST | `/memories` | `content`、`tags[]`、`importance` | 201 + `MemoryOut` | 422 校验失败 |
| GET | `/memories` | `limit` (1-100) | `MemoryOut[]` | 422 |
| GET | `/memories/search` | `q`、`limit` (1-20) | `SearchHit[]` | 400 无可检索 token |

数据状态只有一个：`memories` 表。没有「已删除」「归档」状态，避免第一版就引入状态机。

## 4.4 推荐跟做顺序

1. 建虚拟环境、装依赖、跑起 `/health`。
2. 先写 `MemoryIn` / `MemoryOut` 两个模型，让 `/docs` 能看清字段。
3. 建表：只保留 `content`、`tags`、`importance`、`created_at`、`use_count`。
4. 实现 `POST /memories`，用 Swagger 写入两条中英文混合记忆。
5. 实现 `tokens()`：英文按词、中文按二元组切分。
6. 实现 `score_memory()`：先算命中，再乘重要度，最后加一点时间衰减。
7. 接上 `GET /memories/search`，观察同一 query 下分数排序是否符合直觉。
8. 重复搜索，确认 `use_count` 递增。

## 4.5 设计取舍（为什么这样做）

**为什么不用向量库？**

这一版要验证的是「记忆服务的最小闭环」：写入、召回、反馈。向量库会引入 embedding 模型、维度和相似度阈值三个新变量，出问题时很难判断是打分逻辑还是模型问题。关键词打分先跑通，后续把 `score_memory()` 换成向量相似度即可，路由层不用动。

**为什么中文按二元组切？**

中文没有空格，按字切会让「部署」和「部位」互相误命中；按二元组切在无分词依赖的前提下，能保住大部分短语信号。代价是长词会被拆散，所以标签命中给了 1.5 倍权重，用人工标注补一点精度。

**为什么时间衰减这么轻？**

`exp(-age/30)` 只作为同分时的排序依据，乘的是 `(1 + 0.3 * recency)`。Agent 记忆里「三个月前的架构决策」往往比「昨天的闲聊」更重要，不能让新近性压过重要度。真正该淘汰的记忆，应该由 `use_count` 和使用方策略决定。

**为什么检索后就写库？**

召回即反馈：被用到的记忆更可能再次被用到。这里只累加计数，不做自动降权，避免「一次误召回导致永久沉底」。

## 4.6 常见报错（先查这几条）

| 现象 | 原因 | 处理 |
|------|------|------|
| `RuntimeError: Directory '...' does not exist` | 启动目录不对 | 在项目根目录执行 `uvicorn main:app` |
| `sqlite3.OperationalError: unable to open database file` | `MEMORY_DB` 指向不存在的目录 | 用默认值，或先建目录 |
| 搜索返回空数组 | query 与正文无共同 token | 换更短的关键词，或给记忆补标签 |
| 400 `query has no searchable token` | query 只有单字/符号 | 至少两个字符或一个英文词 |
| 端口被占用 | 8766 已被其他进程使用 | `--port 8767` |

## 4.7 和热点大项目的体力账（可选）

`claude-mem`、`dify` 这类项目把「记忆」做成了完整产品：多存储后端、压缩、注入、可视化。一个人一周内跟不完，也没必要跟。把它们的价值拆成可验证的一小块——写入、召回、反馈——用 150 行跑通，再决定要不要接向量库或换存储，这才是 L1 的正确姿势。
