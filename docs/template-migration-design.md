# 共享模板改版与版本迁移设计

## 1. 问题与目标

同源模板的 8 个角点按 L1–L8 的**位置顺序**与裁片坐标数组逐位对应。改版（重排角点顺序/标签）若直接改 `templates.labels/points`，旧裁片的第 i 个坐标会被按新标签解释，标签与坐标错位；正在录入的旧页面再保存还会把错位坐标写回。

目标：

1. 一个共享模板可发布多个**不可变版本**，一次改版覆盖引用该模板的**多个集合**。
2. 迁移由**逐点映射**驱动（旧标签 → 新标签），发布前可预览每个受影响裁片的重排结果。
3. 迁移期间集合仍可录入、更正裁片，可正常排队研究；每项研究冻结时取到**完整的旧版或新版**，标签与坐标始终对应。
4. 切换前必须把迁移期间发生的更正**追齐（catch-up/rebase）**；中断恢复不得覆盖较新修订（乐观锁）。
5. 同一模板并发发布只允许一个版本生效（迁移级互斥 + 单激活版本约束）。
6. 旧页面保存过期裁片时明确拒绝并提示重载。
7. 映射缺漏或重复时不切换；页面可查看迁移进度、冲突与最终版本。
8. 既有冻结研究及复验说明原样保留，不回写。

## 2. 数据模型（新增 3 表，扩展 1 表）

### 2.1 `template_versions`（模板版本，不可变）

| 字段 | 说明 |
|---|---|
| id | 主键 |
| template_id | 所属模板 |
| version | 模板内递增版本号，从 1 开始 |
| labels / points / convention | 该版本的 8 标签、8×2 参考点、约定 |
| is_active | 该模板当前唯一生效版本（部分唯一索引：每 template_id 仅一条 true） |
| created_at / created_by | 发布审计 |

- 版本行一经发布不再更新（无 update 路径）。
- 部分唯一索引（PostgreSQL）：`UNIQUE(template_id) WHERE is_active`；SQLite 测试回退为 `is_active` 普通唯一索引，服务层同样保证单激活。
- `(template_id, version)` 唯一。
- 上线引导（lifespan 幂等）：为每个现存模板补 version=1 的首版（active），并把其下所有裁片 `template_version=1`。

### 2.2 `template_migrations`（一次改版发布，跨多集合）

| 字段 | 说明 |
|---|---|
| id | 主键 |
| name | 名称，唯一，便于留痕 |
| template_id | 改版的共享模板 |
| from_version_id / to_version_id | 源/目标版本（同模板，目标版本号更大） |
| status | `draft` / `in_progress` / `conflict` / `completed` / `cancelled` |
| label_mapping | JSON：`{旧标签: 新标签}`，8 项 |
| point_mapping | JSON：`[新位置i] = 旧位置j`，由标签映射预计算 |
| summary | JSON：进度与冲突统计（applied/pending/failed/stale、各集合计数、错误明细） |
| created_by / created_at / updated_at / finished_at | 审计与时间线 |

- 同模板同时至多一条非终态迁移（`draft/in_progress/conflict`），服务层加锁判定（并发发布互斥）。
- 终态：`completed`、`cancelled` 不可再变更。

### 2.3 `template_migration_items`（每个受影响裁片一行）

| 字段 | 说明 |
|---|---|
| id | 主键 |
| migration_id / specimen_id | 关联 |
| collection_id | 冗余，便于按集合聚合预览 |
| status | `pending` / `applied` / `failed` / `stale` |
| before_points / after_points | JSON 8×2，重排前后快照（预览即写入 after） |
| source_specimen_version | 生成/应用该行时裁片的版本号 |
| message | 失败原因等 |

- `UNIQUE(migration_id, specimen_id)`；`UNIQUE(migration_id, collection_id, specimen_id)` 由前者蕴含，保留前者即可。

### 2.4 `shape_specimens` 扩展

- `template_version: int NOT NULL DEFAULT 1`：该裁片坐标当前对应的模板版本（乐观锁/新鲜度令牌）。
- 保存（新增/更正）时：
  - 新增：服务端强制取模板当前激活版本，忽略客户端值。
  - 更新：请求须携带其读取时的 `template_version`；与库中不一致 → **409**，提示页面数据已过期、请重载后再编辑。同时校验点数仍为 8×2。

## 3. 映射与重排规则

- 映射是标签级双射：键为源版本 8 个标签且不缺漏、不重复；值为目标版本 8 个标签，集合必须恰好相等（8 个新标签全覆盖、无重复）。
- 位置映射：对目标顺序的每个位置 i，`point_mapping[i] = j`，其中源标签 j 映射到目标标签 i。
- 重排：`after[i] = before[point_mapping[i]]`，即坐标随标签一起搬到新位置，**只换位置、不改数值**。允许恒等映射（标签不变、仅参考点调整）。
- 预览：为模板下每个集合的每份现存裁片生成 item，写 `before/after`，初始 `pending`；不触碰裁片本体。
- 校验失败（缺漏/重复/非双射）在创建与激活两个时点都拒绝，状态不推进。

## 4. 迁移生命周期

```
draft ──activate──▶ in_progress ──全部 applied──▶ completed
  │                     │  ▲
  │                     ▼  │ rebase/catch-up 后重试
  │                  conflict（存在 failed/stale）
  └──── cancel ───────────────────────────▶ cancelled（终态）
```

1. **创建（draft）**：校验目标模板下无其他非终态迁移；创建目标版本（不可变）；按现存裁片生成 pending 预览 items；写 summary。此阶段裁片仍属旧版，录入/更正/研究不受阻。
2. **激活/切换**（editor）：
   - 重算映射双射；存在 `failed/stale` 或非 `pending/applied` 之外的脏 item 则拒绝并置 `conflict`。
   - 以单事务 + `SELECT ... FOR UPDATE`（PG；SQLite 回退普通事务）锁定模板、迁移与该模板全部裁片，再次确认无并发非终态迁移、目标版本未被他人激活。
   - 逐 item 条件更新：仅当裁片当前版本 == item 记录的源版本（且 item 仍 pending）时重排并把 `template_version` 升到目标版本；否则记 `stale`（迁移期间被更正过）。
   - 全部成功：激活目标版本（旧 active 置 false）、迁移 `completed`、写 finished_at 与 summary。任一未应用：事务回滚版本切换，迁移置 `conflict`，已应用的 item 保留进度（不回滚裁片，因同版本内重排幂等且可重入），等待追齐后重试。
3. **追齐 rebase**（editor，对单条 failed/stale item）：按当前裁片坐标与映射重新生成 before/after，刷新源版本令牌，状态回 `pending`；若裁片在迁移创建后新增，则补建 item。激活前 summary 必须无 failed/stale。
4. **中断恢复**：激活设计为可重入。worker/API 中断后重试，条件更新保证不会覆盖比 item 令牌更新的裁片修订；已 applied 的跳过。
5. **取消**（editor，仅 draft/conflict）：迁移 `cancelled`，不动任何裁片与激活版本；其目标版本保留为不可变历史，但不激活。

### 并发：只允许一个版本生效

- 服务层在创建/激活处对同一 `template_id` 检查非终态迁移并加行锁/事务串行化。
- `template_versions` 部分唯一索引保证每模板至多一个 active 版本。
- 激活经 Redis 队列 `shapes:migrations` 交单 worker 执行（与 run 同构：Redis 仅唤醒，DB 为权威，worker 周期扫描 in_progress 兜底），天然单消费者；API 直接调用也走同一把事务锁。

## 5. 研究（run）冻结口径

- 创建 run 时读取集合当前激活模板版本的 labels/points 与该版本下全部裁片，写入 `snapshot.template`（含 `version`）与 `snapshot.specimens`。
- 迁移期间：尚未切换 → 取完整旧版；切换后 → 取完整新版。不存在半版本快照。
- 既有 run 的 snapshot/result、artifacts 文件、复验说明与导出 CSV 完全不回写（数据已是 JSON 快照）。
- 指纹算法不变；snapshot 内含版本号，新旧版指纹天然区分。

## 6. 过期保存拒绝

- 前端裁片表单携带读取时的 `template_version`（隐藏字段）。
- 后端更新若发现版本令牌落后（迁移已切换或他人更正），返回 409：`裁片对应模板已改版（v旧→v新），页面数据已过期，请重载后按新角点顺序编辑`。
- 前端捕获 409 后提示并自动重载集合数据，杜绝旧坐标覆盖新顺序。

## 7. API

| 方法/路径 | 权限 | 作用 |
|---|---|---|
| GET `/templates` | 登录 | 模板列表，附 current_version |
| GET `/templates/{id}/versions` | 登录 | 版本时间线 |
| PUT `/templates/{id}` | editor | 仅可改 name/convention；改 labels/points 返回 422 指引走迁移 |
| GET `/migrations` | 登录 | 迁移列表（含 summary） |
| POST `/migrations` | editor | 创建改版与预览（draft） |
| GET `/migrations/{id}` | 登录 | 详情 + items（进度/冲突/前后坐标） |
| POST `/migrations/{id}/activate` | editor | 激活切换（in_progress→completed/conflict） |
| POST `/migrations/{id}/items/{item_id}/rebase` | editor | 追齐单条冲突 |
| POST `/migrations/{id}/cancel` | editor | 取消 |
| GET `/specimens?collection_id=` | 登录 | 输出增加 template_version |
| POST/PUT `/specimens` | editor | 携带/校验 template_version，过期 409 |

## 8. 前端

- 新增第 7 页「模板改版」（`/migrations`）：模板选择 → 新建迁移（填新标签/参考点/映射，自动校验双射并提示缺漏/重复）→ 受影响裁片逐点预览（ShapeCanvas 前后对比 + 映射表）→ 激活/追齐/取消；展示进度、冲突清单、最终版本与时间线；2.5s 轮询 in_progress/conflict。
- 「角点与基准」模板表单收敛为 name/convention 编辑，标签/坐标只读并标注当前版本，提供改版入口。
- 裁片表单带版本令牌；409 时明确报错并自动重载。
- 复用 PageHeading/StatusBadge/ErrorNotice/ShapeCanvas/useTask/usePolling/store 约定，样式沿用现有纸面风格。

## 9. 测试（SQLite 本地 + PG 兼容）

后端 pytest（TestClient + SQLite，JSON/事务/条件更新均用通用 SQL）：

1. 首版引导：旧库启动后模板有 v1、裁片 template_version=1。
2. 映射缺漏/重复/非双射 → 创建或激活被拒，不切换。
3. 完整迁移：两集合 60 份裁片逐点重排正确，active 切到 v2，标签坐标对应。
4. 迁移期间更正 + 激活 → 该裁片 stale/conflict；rebase 追齐后再激活成功，更正不丢失、不被覆盖。
5. 中断恢复：模拟部分 applied 后重新激活，最终一致且不覆盖新修订。
6. 并发：同模板两个非终态迁移第二个被拒；始终只有一个 active 版本。
7. 旧页面过期保存 → 409 且提示重载；刷新后保存成功。
8. 研究口径：迁移前后各建 run，snapshot 分别完整冻结旧/新版；旧 run 与复验说明保持原样。
9. 取消：draft/conflict 可取消且无副作用；终态不可再操作。
10. 权限：viewer 写操作 403。

前端 `tsc --noEmit && vite build` 保证类型与构建通过。
