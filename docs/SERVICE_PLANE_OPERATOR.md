# minicc-cloud 服务面运维手册

这份文档讲一件事：**怎么把服务面运行起来、它到底答了什么、验证依据是什么。**

以下命令都在本仓库 `main@393b4f7`（含 M8-T721..T731 合流；M8-T732 README 服务面指针）上实测；输出原文来自实机 curl/Invoke-WebRequest。

## 1. 模块拓扑与端口

| 模块 | 端口 | 职责 |
| --- | --- | --- |
| `minicc-cloud-registry` | 8761 | Eureka 服务发现 |
| `minicc-cloud-config` | 8888 | Config Server（native），`config-repo/` 下的共享/服务专属 yml |
| `minicc-cloud-inspector` | 8081 | 只读工作区诊断：`/api/changes`、`/api/capabilities` |
| `minicc-cloud-tasks` | 8082 | 只读任务历史（SQLite `tasks.db`），`db` 来自 `MINICC_STATE` |
| `minicc-cloud-gateway` | 8080 | 路由 + Resilience4j 熔断，`/api/changes`、`/api/tasks*` |
| `minicc-cloud-bridge` | —（库） | 生命周期管理 Python 子进程，凭据脱敏 |

服务面不重写 Python 引擎；桥接层是唯一缝隙。`mvn -B test` 覆盖六个模块；CI 的 `Service plane tests (mvn)` 只在 `minicc-cloud/**` 改动时触发。

## 2. 验证 tasks 服务：standalone 模式

以下步骤已逐步跑通；被测环境为 JDK 25 + Maven 3.9，全部在本机对话中执行：

```powershell
# 1. 造一个探针用的 tasks.db（绝不读写真实 .minicc/）
python - <<'PY'
import sqlite3, json, pathlib
root = pathlib.Path(r'C:\path\to\probe')
root.mkdir(parents=True, exist_ok=True)
db = root / 'tasks.db'
conn = sqlite3.connect(str(db))
conn.execute('CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY, created_at DOUBLE, workspace_path TEXT, payload TEXT)')
payload = {'task_id': 't-demo-1', 'status': 'completed', 'preview': 'demo task', 'created_at': 1762720000.0}
conn.execute('INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?)', ('t-demo-1', 1762720000.0, '/tmp/ws-demo', json.dumps(payload, ensure_ascii=False)))
conn.commit()
conn.close()
PY

# 2. 启动（config server 未启动时不影响本机返回；以 standalone 运行）
cd minicc-cloud\minicc-cloud-tasks
set MINICC_STATE=C:\path\to\probe
mvn spring-boot:run
```

启动日志出现 `Started TasksApplication in ... seconds` 即可。容器读取 `${MINICC_STATE}/tasks.db`（表 `tasks`：`task_id TEXT PRIMARY KEY, created_at DOUBLE, workspace_path TEXT, payload TEXT`）；`mode=ro` 打开。

## 3. 三种调用实录

```text
GET http://127.0.0.1:8082/api/tasks?limit=5
```

```
HTTP 200
[{"task_id":"t-demo-1","status":"completed","created_at":1.76272E9,"workspace_path":"/tmp/ws-demo","preview":"demo task for the service-plane operator guide"}]
```

```text
GET http://127.0.0.1:8082/api/tasks/t-demo-1
```

```
{"task_id":"t-demo-1","created_at":1.76272E9,"workspace_path":"/tmp/ws-demo","payload":{"task_id":"t-demo-1","status":"completed","preview":"demo task for the service-plane operator guide","created_at":1.76272E9}}
```

`limit` 超过服务端天花板：

```
GET http://127.0.0.1:8082/api/tasks?limit=999

StatusCode: 200
X-Minicc-Tasks-Truncated: true
X-Minicc-Tasks-Limit: 100
[{"task_id":"t-demo-1", ...}]
```

响应头 `X-Minicc-Tasks-Truncated: true` 表明被截断；`X-Minicc-Tasks-Limit: 100` 表明生效天花板来自 Config Server 的 `minicc-cloud-tasks.yml`（`spring.cloud.config.import: optional:configserver:${CONFIG_SERVER:...}`），本地 standalone 时由 `MINICC_TASKS_MAX_LIMIT` 环境变量或 `100` 兑底。

## 4. 环境变量契约

### tasks（`minicc-cloud-tasks`）

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `MINICC_STATE` | `../.minicc` | `tasks.db` 所在目录 |
| `MINICC_TASKS_MAX_LIMIT` | `100` | 客户端 `limit` 服务端天花板（standalone） |
| `CONFIG_SERVER` | `http://localhost:8888` | 可选；未启动时按 standalone |
| `EUREKA_ZONE` | `http://localhost:8761/eureka/` | 可选；未启动 `Registration failed` 警告后 standalone |

### inspector（`minicc-cloud-inspector`）

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `MINICC_ALLOWEDROOTS` | `/workspaces` | 路径准入白名单；外面一律拒绝 |
| `EUREKA_ZONE` | `http://localhost:8761/eureka/` | 可选 |
| `CONFIG_SERVER` | `http://localhost:8888` | 可选 |
| `MINICC_BRIDGE_CMD` | 自动 | Python CLI 调用方式（例如 `python -m minicc`） |

### gateway（`minicc-cloud-gateway`）

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `EUREKA_ZONE` | `http://localhost:8761/eureka/` | 寻址 inspector / tasks |
| `CONFIG_SERVER` | `http://localhost:8888` | 可选；可覆写 `response-timeout-seconds` / `connect-timeout-ms` |

## 5. 故障排查

- Q：`TaskStoreUnavailableException` →「任务库读取失败」
  A：`MINICC_STATE` 没指到 `tasks.db` 目录，或文件不存在/损坏。建文件或修正 `MINICC_STATE`。
- Q：curl 返回 404
  A：`{taskId}` 不在库里。任务 ID 由 Python 引擎在 `minicc/task_manager.py` 生成，手填必 404。
- Q：`limit` 被静默钳到 100
  A：`X-Minicc-Tasks-Limit: 100` 就是这个语义；把 `MINICC_TASKS_MAX_LIMIT` 或 Config Server 放大。
- Q：日志 `Registration failed ... Connection refused`
  A：Eureka 不可达。服务面 standalone 模式不依赖注册中心，所有 API 仍可用。
- Q：inspector 返回空数组
  A：只读 `ALLOWEDROOTS` 外路径无法诊断；设置 `MINICC_ALLOWEDROOTS` 白名单，或改挂 `/workspaces/target:ro`。

## 6. Full stack

```powershell
docker compose -f minicc-cloud/docker-compose.yml config --quiet   # rc=0 无错
```

仅解析，不构建。真正启动：`mvn -DskipTests package -f minicc-cloud/pom.xml` → `docker compose -f minicc-cloud/docker-compose.yml build && up`。

## 7. 相关文件

- `minicc-cloud/README.md`
- `minicc-cloud/minicc-cloud-config/src/main/resources/config-repo/application.yml`（共享配置）
- 合流账本：`docs/ROADMAP_TO_PRODUCT.md`
- 运行/构建 CI：`.github/workflows/ci.yml`
