> 当前版本 0.1.7（2026-10-13）的独立结论和实际测试见 [AUDIT-017](AUDIT-017.md)。下文保留历史记录，其中旧版本“未修复”说明不代表本版；GitHub/RH 状态以实际交付报告为准。

# API + A2 BackgroundBridge 集成验证（0.1.6）

日期 2026-10-12；原 GitHub main：`0f433e9adbb37b36d0ade27c2ae5e42196a42e36`。原仓库完整 Git bundle 和 source ZIP 在提交前保存，备份 SHA256 在本次交付 backup-record.json。只在任务工作目录中的本仓库 clone 上修改。

## 集成内容

根 __init__.py 将 API 与 h3_background_bridge 子包的两个映射合并为八个节点，同时保留 STORE、管理路由和 WEB_DIRECTORY。API 的 nodes.py 与 h3_adapter 所有 Python 文件逐字节去除 CRLF 差异后与原 GitHub 版本一致；web/h3_adapter.js 与原 Git blob 字节完全相同，两个手动按钮保留。运行依赖补充 NumPy。发布 allowlist 已纳入 Bridge、集成工作流、依赖、属性、测试与安装说明。

未改二次取证的 Guard。Recipe 原先调用 credential_generations()，在当前 GitHub ConfigStore 上复现 TypeError：缺少 config 参数。仅将其改成同一 ConfigSnapshot 的 credential_generations、revision，并在 credential 捕获时传 expected_revision。没有回退当前适配器凭据快照、代际、冷却或账本实现。Key 更换会改变 API 配置摘要，Z 参数更换只改变背景修订；捕获期间配置改变被拒绝。

## 实际运行结果

| 本地检查 | 结果 | 范围 |
|---|---|---|
| 完整 Python unittest discovery | 180/180 PASS，0 失败/错误/跳过 | 原适配器 174 项 + 新集成 6 项，含三个 Git 本地夹具 |
| JS 前端回归 | 6 套 PASS | 原前端文件未改，配置、密钥、模型和并发操作 |
| 独立 API/TCP Mock | 27 类 PASS | localhost 真实 HTTP、发现、主备、mask、异步、账本重放 |
| 真实官方 ComfyUI loader | PASS，八节点、路由、六文件哈希 | 单个本仓库插件；有/无 MASK，2 次 Mock POST、缓存重放、真实 Save/Preview |
| 二次取证 Bridge 回归 | 10/10 PASS | 当前集成适配器 + Bridge + 只读既有 Core |
| 真实 ComfyUI 调度 | 17 个场景满足预期，12 次 Mock POST | API/Bridge/Core 实代码，Qwen/Z CPU 替身，H3 输入边界观察器 |
| 发布包包含与版本校验 | PASS | Bridge/工作流实际入 ZIP、六文件精确 SHA256、源码篡改拒绝 |
| 工作流结构 | PASS | 121 nodes / 251 links 与取证候选完全相同，仅 extra.integrated_repository 新增 |
| 受保护文件 | PASS | 114 个既有明确列入基线文件 + 本次取证候选哈希不变 |

调度覆盖 A/B/A 回访、多窗输入、同环境不同视角、API 拒绝/不确定/空图、不重复 POST、Z 失败恢复、hidden PROMPT 的 0.86→0.50、异步 GET 恢复、远端失败终结、宽高比错误停止。测试中 success=false 是预期阻断结果；PASS 是断言符合预期，不是所有场景都应成功出图。

失败/等待/未知状态及不同宽高比输出由 APIGuard 阻断，不进入 Qwen/Z/H3 消费边界。READY 仅表示完成整条流水线，不认证图像质量。生产模型、真实供应商去人物、完整 H3 MP4 和 RH 云端任务均未执行。收费请求数为 0。

## 精确版本校验

Bridge 运行时仍验证以下六个文件；.gitattributes 固定校验文件 LF，禁止删除校验掩盖失配。Bridge 源码 SHA256：`d350241060daccd0e45478d98737b266b5814bee3bd015e7a6c56569fb625297`。

| 文件 | SHA256 |
|---|---|
| `nodes.py` | `af3f9bf18242edaf4dee533493229d82af25030e5beaea0254fd44f1f5ba1694` |
| `h3_adapter/engine.py` | `fbf9fdd00ecb80887b65d274469f336cfd3e445d0b909a0a585236a62f0e4b69` |
| `h3_adapter/config.py` | `364b04f648c9c0c70e86c4447623f19c5902c147d8efac5fe36e0a3dbcab21b4` |
| `h3_adapter/protocol.py` | `61956b22c394870be8866ad0868144c76903f1a831b99bb498296887c38f0ce0` |
| `h3_adapter/ledger.py` | `a839e8037a967560a0c72d32887f8b235b039faa7f8a59d1677fa29aa5ce7556` |
| `h3_adapter/routes.py` | `c57d4ff308ef1d4a2232d193122751c665c54dc92cb5c9c52b1e4e8bb9e15043` |

原适配器已知 HTTPX 解压前内存限制缺陷，以及独立 API 失败零张 IMAGE 直接接标准 Save/Preview 的 IndexError 路径仍未修复。本次融合通过 Guard 阻断其失败传播，不声称解决适配器的全部已知缺陷。既有 H3 Core/模型等运行依赖与 RH 权限边界见 RH-INTEGRATED-INSTALL.md。

本次上传源文件已检查：不含真实 Key、活动 provider 配置、私密账本、secrets.private.json、SQLite/runtime、__pycache__ 或临时测试数据；所有测试凭据均为人工合成本机 Mock。Git 和 ZIP 均采用明确公开文件集合，活跃配置不提交，发布 ZIP 只提供全禁用占位配置。推送后的精确 SHA、远端重新 clone 和文件逐项比对由交付报告记录，不能把此本地报告当作 RH 验收。
