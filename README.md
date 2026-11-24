# fastapi-agent-memory

CSDN 周三热点配套项目：**带时间衰减的 Agent 记忆检索 API**（FastAPI + SQLite，零外部服务）。

## 环境

- Python 3.10+
- Windows / macOS / Linux

## 安装

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

## 启动

```bash
uvicorn main:app --host 127.0.0.1 --port 8766
```

Swagger：`http://127.0.0.1:8766/docs`

## 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/memories` | 写入一条记忆（内容 / 标签 / 重要度 1-5） |
| GET | `/memories` | 按时间倒序列出记忆 |
| GET | `/memories/search?q=` | 关键词检索，按相关度 + 重要度 + 时间衰减排序 |

## 验收（跟做清单）

1. `GET /health` → `{"status":"ok","db":"memories.db"}`
2. `POST /memories` 写入两条记忆（一条高重要度、一条低重要度）
3. `GET /memories/search?q=部署` → 命中并按分数降序
4. 再搜一次同一关键词 → 结果的 `use_count` 增加

```bash
curl -s -X POST http://127.0.0.1:8766/memories ^
  -H "Content-Type: application/json" ^
  -d "{\"content\":\"生产部署必须走蓝绿发布\",\"tags\":[\"部署\",\"ops\"],\"importance\":5}"

curl -s "http://127.0.0.1:8766/memories/search?q=部署"
```

## 关联文章

**项目搭建详解**：[docs/GUIDE.md](docs/GUIDE.md)  
CSDN 稿件见博主「周三热点实战」系列；**项目名 = 本仓库名**。
