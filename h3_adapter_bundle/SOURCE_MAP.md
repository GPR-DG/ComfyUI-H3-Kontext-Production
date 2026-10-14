> 当前版本 0.1.7（2026-10-13）的独立结论和实际测试见 [AUDIT-017](docs/AUDIT-017.md)。下文保留历史记录，其中旧版本“未修复”说明不代表本版；GitHub/RH 状态以实际交付报告为准。

> 当前增量更新：2026-10-12，开发测试候选。原模块结构与数据流保持，以下补充优先于历史发布判断。
>
> routes.py：管理授权先校验 Origin/管理设置，再按 UTF-8 bytes 常量时间比较 token；非 ASCII 失败返回授权拒绝。config/key/models 仍经 ConfigStore/CAS，不公开 Key。
> web/h3_adapter.js：request 清理本次坏 token；dialog 提供关闭状态；openManager 密钥写入串行，配置保存成功后更新 revision/刷新 keys 并保留未保存编辑警告。模型切换参数清理仍保留。
> engine.py：下载/归一化结果 → 临时写入 → replace → finally 清理临时文件 → 原账本完成流程；写入失败仍保留 result_ready 与预算预留，后续恢复同任务。
> 未变更 config.py、ledger.py、protocol.py、nodes.py；protocol 解压分配与 nodes 空 IMAGE 仍阻断稳定发布。新增 tests/test_development_upload.py 与 tests/test_development_frontend.mjs 进入原构建白名单。

# SOURCE_MAP

审计日期：2026-10-11。以下结论来自全部原始 Python/JS/MJS 源文件、配置、节点注册、测试与构建脚本的逐文件阅读；历史 AUDIT/日志只作对照，不作代码正确性证据。原始 41 个源文件（36 Python、5 JS/MJS，310047 字节），本次新增 3 个验证源文件。最终发行源码与文档逐文件哈希见 SOURCE-MANIFEST.json。

## 核心模块、调用关系与数据

| 文件 | 职责与关键入口 | 调用关系 | 数据流与持久化 |
|---|---|---|---|
| __init__.py | ComfyUI 入口，NODE_CLASS_MAPPINGS、显示名、WEB_DIRECTORY；宿主存在时注册管理路由 | 导入 nodes；调用 routes.register_routes | 注册唯一 H3ImageEdit；不修改其他节点或原工作流 |
| nodes.py | H3ImageEdit.INPUT_TYPES/edit；png_inputs/image_tensor；标准 IMAGE/MASK 转换 | ConfigStore → Engine.edit | BHWC float IMAGE → PNG bytes；MASK 白色编辑区 → 透明 alpha PNG；返回 BHWC IMAGE、provider_model STRING、status_report STRING |
| h3_adapter/config.py | validate、atomic_json、settings_lock；ConfigStore.load/save/public/save_key/credential/revision | 节点、Engine、管理 routes 使用 | providers.json 为非秘密配置；secrets.private.json/环境变量为 Key；锁内 revision/generation 捕获；删除凭据转 retired，代际递增 |
| h3_adapter/engine.py | fingerprint、能力/参数/预算筛选、主备单次提交、_recover、结果缓存 | ConfigStore、Journal、Protocol；Pillow 检验 PNG/结果 | 输入指纹含图/Mask/prompt/alias/provider/params/nonce；请求身份 → ledger → POST/GET → 图片缓存 → report |
| h3_adapter/ledger.py | Journal.begin/reserve/mark/reject/cooldown/available | Engine 唯一生产调用者 | SQLite requests/health；请求主键唯一；BEGIN IMMEDIATE 原子提交预留；持久预算、受理任务/结果快照、冷却；旧 health 表新增可空 identity 列 |
| h3_adapter/protocol.py | Protocol.submit/poll/result/discover、HTTP 请求/认证/模板/上传 | Engine 与 routes；HTTPX | multipart 或 JSON 将 IMAGE/MASK/model/prompt/params 映射到网络；无客户端自动付费重试；GET 轮询和结果获取；限制响应体/结果主机/认证传播 |
| h3_adapter/routes.py | 配置读写、Key 保存、模型发现管理接口 | ConfigStore；异步 to_thread 调用 Protocol.discover | 授权后接收有界 JSON；公开配置只给 Key 是否存在；revision 防旧窗口覆盖；发现使用读取时 revision |
| web/h3_adapter.js | ComfyUI 扩展、供应商/Key 管理、模型选择、报告显示 | app.registerExtension；api.fetchApi → routes | Key 只进入私密保存 POST；模型能力/价格不从发现 ID 推断；切换实际供应商/ID/alias 清空参数；发现 generation 防迟到响应覆盖 |
| scripts/build_release.py | 精确 RELEASE_FILES 白名单、禁用配置初始化、manifest 和 ZIP | 仅读取发行名单；SHA256 复核 | 不采集 runtime/秘密/未知文件；providers.json 由公开 example 生成；构建器不冒充运行了测试 |
| scripts/mock_server.py、tests/mock_api.py | 本机免费 Mock API、请求捕获 | 开发演示、回归、官方宿主验证 | 只监听 localhost，固定合成图片与不可用凭据；不转发到真实供应商 |
| scripts/independent_http_smoke.py | 独立真实 TCP 协议/业务断言，27 类场景 | ConfigStore/Engine/Protocol；自己实现 HTTP peer | 捕获实际 multipart/JSON、POST 次数、轮询和费用预留；输出验证 JSON |
| scripts/verify_comfyui.py | 使用已有官方宿主源码的导入与节点执行验证 | 官方 nodes.load_custom_node、PromptServer、SaveImage/PreviewImage | CPU torch、有/无 Mask、缓存重放；文件只进显式 scratch；2 次编辑 POST |
| h3_adapter/__init__.py | 子包标识 | Python 相对导入 | 无运行逻辑 |

供应商是 providers 数组中的配置字典，没有隐藏的 Provider 单例或独立供应商类。模型由每家自己的 models[逻辑别名] 解析；默认参数、Mask 编码、报价取当次供应商模型，不从主供应商复制。Secret 与模型发现缓存不会写进 ComfyUI 工作流。

## 主请求与恢复链

```text
ComfyUI IMAGE [B,H,W,C] + MASK [B,H,W]
  → nodes.png_inputs → PNG images / mask
  → Engine.edit → ConfigStore.load（锁内 revision + generations）
  → fingerprint（用户输入 + nonce）→ Journal.begin
  → completed: 检查缓存并返回；submitting/uncertain: 阻止重新 POST
  → accepted/result_ready: 按原 provider/model/credential 任务快照恢复
  → ready: 顺序选主/备、检查能力/参数/估价/冷却
  → credential（验证读取时 revision）→ model.defaults + params
  → Journal.reserve（SQLite BEGIN IMMEDIATE，POST 前落盘）
  → Protocol.submit（单次付费 POST）
  → 明确未发出/配置允许的拒绝: reject → ready → 下一家
  → 未知/超时/不完整成功响应: uncertain → 停止备用提交
  → 异步 task_id: accepted → 只 GET 原任务
  → 有结果定位: result_ready → 下载/校验 → 缓存 → completed
  → nodes.image_tensor → IMAGE + 两个 STRING
```

配置或供应商变化不会自动制造新的付费身份：同一输入/nonce 使用原任务/缓存，这是已有合同。新付费意图必须明确改变 nonce 或请求输入。防重依赖同一持久化 SQLite/runtime；request_id 没有发送到供应商幂等 Header，不能承诺分离数据库之间防重。

## 配置与发行辅助文件

| 文件 | 实际用途 |
|---|---|
| config/providers.example.json | 默认禁用的多供应商配置，逻辑别名、能力、参数、认证、价格和主备 |
| config/protocol-variants.example.json | multipart、JSON 内联、JSON 异步、上传后引用四种公开示例 |
| config/providers.mock.json | 仅本机免费演示的启用 Mock 配置 |
| config/providers.json | 本地活动配置，Git 忽略；ZIP 构建覆盖成禁用公开示例 |
| requirements.txt、pyproject.toml | 运行依赖、Python 下限、0.1.5 版本；aiohttp/NumPy/Torch 由宿主提供 |
| requirements-dev.txt | 回归所需的开发依赖；官方宿主验证另需完整宿主依赖 |
| examples/image_edit_minimal.json、image_edit_minimal_api.json | 新的独立最小工作流，不覆盖原 H3 工作流 |
| .gitignore、licenses/、LICENSE | 本地秘密/runtime/备份忽略；自有与第三方许可 |

## 测试源码阅读范围

每个文件均已阅读其真实断言；数量与 PASS 仅作执行结果，不代替源码判断。

| 文件 | 检查职责 |
|---|---|
| test_config.py、test_round2_config.py | 校验、凭据隔离、原子配置/revision |
| test_engine.py、test_round2_scheduler.py | 主备顺序、能力、费用上限、固定路线、防重 |
| test_ledger.py、test_round2_concurrency.py | SQLite 原子 claim、线程/进程并发、累计预算 |
| test_protocol.py、test_round3_protocol.py | 真实字段映射、HTTP/模板/上传、结果/认证边界 |
| test_nodes.py、test_masks.py、test_round2_images.py | Comfy 端口、张量/Mask/尺寸和图片边界 |
| test_routes.py、test_round3_routes.py | 管理授权、JSON 边界、秘密不回显、revision 冲突 |
| test_review.py、test_round3_state.py | 未知受理、终态、恢复与冷却状态机 |
| test_round4_credentials.py | 身份/Key/旧任务恢复、配置与 Key 读取竞态 |
| test_round4_health.py | 本地错误与供应商故障分类、有限冷却 |
| test_round4_parameters.py | 模型保留字段、multipart 参数、默认值与报价 |
| test_round4_recovery.py | 并发轮询、终态不可回退、异步结果恢复 |
| test_followup_contracts.py、test_round5_contracts.py | 后续补充的协议/配置/防重合同 |
| test_round2_release.py、test_round4_release.py、test_round5_release.py | Git/ZIP 白名单、禁用配置、秘密和备份隔离 |
| test_frontend.mjs、test_frontend_review.mjs | 管理 UI 回调、原行为与工作流隔离 |
| test_round3_frontend.mjs、test_round4_frontend.mjs | 迟到发现响应、表单保存、模型映射和参数 |
| test_final_identity.py | 本轮 8 项提交/发现/恢复/冷却身份与 schema 迁移回归 |
| test_final_frontend.mjs | 本轮 6 个切换参数回归；直接执行生产 JS |

旧测试没有改动；本轮回归先在待修代码上失败，再验证最小补丁。

## H3K 交付增量

- `h3_kontext_bridge/nodes.py`：八类 H3K 原业务实现和已复現的最小修复。
- `h3_kontext_bridge/core-required-sha256.json`：五个精确 Core 文件的 LF-normalized pin。
- `__init__.py`：保留 API/A2 注册、WEB_DIRECTORY、原路由并追加 H3K。
- `tests/test_h3k_delivery.py`：端口、immutable proof、失败阻断、cleanup 与 hash 回归。
- `docs/H3K-DELIVERY.md`、`docs/H3K-TARGET-PORTS.json`：业务审计、部署边界及目标 JSON 端口合同。
