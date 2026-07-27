# 本地容器部署

该 Compose 运行可执行的单节点平台基线：API、工作台、SQLite 元数据存储和按需启动的 OpenCode Server。Git 需要在源仓库写入 worktree 元数据，因此仓库挂载不是只读；OpenCode 进程只进入容器临时 worktree，平台在运行前后校验源 HEAD、worktree HEAD 和 Patch 路径，不把宿主仓库作为 Agent 工作目录。

```bash
export CODE_ONTOLOGY_API_TOKEN="$(openssl rand -hex 32)"
export REPOSITORY_ROOT="/absolute/path/to/repositories"
docker compose -f deploy/docker-compose.yml up --build
```

打开 `http://127.0.0.1:8080`，在工作台输入 API Token 和 Requirement ID。

生产扩展时应将 SQLite 替换为 PostgreSQL、将图快照投影到 Fuseki/Neo4j、将 Artifact 放入对象存储，并将 Agent Run 调度为带网络策略和短生命周期卷的独立 Job。当前 Compose 不虚构这些尚未连接的外部依赖。
