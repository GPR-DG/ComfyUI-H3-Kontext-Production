# 0.1.7 独立二次取证与修复后复审（2026-10-13）

基线：原仓库备份 0f433e9adbb37b36d0ade27c2ae5e42196a42e36；本地集成 0.1.6 为 bdf29b4830cfda5d97eadbde1212c2ca3e6bfe25。两轮均重新读取实际源码并执行探针；历史报告只作设计合同对照。以下判定描述 0.1.6 的风险及 0.1.7 处理，不能解释为 RH 已验收或 GitHub 已推送。

| 项目 | 裁决及源码、调用链、复现 | 处理与业务边界 |
|---|---|---|
| A | CONFIRMED。H3A2Recipe.run 原来把全部供应商摘要放进 api_prompt → Engine.fingerprint → Journal 新请求。仅改未使用备用模型，主供应商额外 POST=1。 | 仅所选供应商/模型/请求参数构成 API nonce；Prompt 保持去人物原文。未使用备用 Key/模型变化，Recipe 三输出不变、总 POST=1。保留主备、凭据检查、账本和 GET 恢复。 |
| B | CONDITIONAL（共享账本条件下缺陷已复现）。Engine.edit 原 completed 分支直接读结果；不同 Key、另一 ConfigStore 同 runtime 可读前账号缓存。独立安装、租户独立目录无此触发条件。 | authorize_snapshot 在结果读取/任务恢复前校验原 Key 或明确同账号声明；跨账号阻断，不关闭缓存、不自动 POST。不同账号必须独立配置/runtime/OS 隔离。 |
| C | CONDITIONAL。同站换 Key 原合同允许恢复，真实 GET 使用新 Key；同账号合理，不能直接认定所有轮换有错。Base URL 相同不证明账号相同。 | 原 Key 指纹或已有快照中的 account_id + 原身份/代次允许恢复。未证明账号时 awaiting_result，不 GET/POST；恢复原 Key 后仅 GET。account_id 是管理员非密钥声明，须在任务受理前正确设置，不是认证系统。 |
| D | CONFIRMED。Protocol._request 原 iter_bytes 在上限检查前由 HTTPX 解压。8 MiB 解压体、1 KiB 上限真实 TCP 探针峰值 22,457,459 bytes。 | iter_raw + 有上限的 gzip/zlib/raw-deflate 解压；同探针峰值 115,239 bytes。编码体/解码体均受 max_response_bytes（默认 64 MiB）限制；块最多 64 KiB，检查 deadline/完整流。图片字节 64 MiB、40,000,000 像素上限保持。合法压缩回归通过；不自动重发 POST。 |
| E | CONFIRMED（独立 Save/Preview）；“融合失败会 READY/重付费”假设 REJECTED。原节点返回零 IMAGE，标准消费者会异常；Guard/Finish 失败阻断有效。 | 有 ExecutionBlocker 的真实 ComfyUI 失败 IMAGE 输出阻断，两个文本与 UI 报告保留；5 个标准 Save/Preview 失败场景没有实际消费者执行或图片输出。无 ComfyUI 的库调用仍空 IMAGE。主机须支持 comfy_execution.graph.ExecutionBlocker。队列 status_str=success 可能仅代表调度结束，必须读 API 状态与实际输出。 |
| F | REJECTED。H3A2APIGuard.run 已用整数叉乘检查比例；相同比例不同分辨率允许等比缩放，不同比例及近似但不相同比例拒绝。image 校验单 RGB batch/finite/[0,1]/尺寸；API 图片还有字节/像素上限。 | 不修改 Guard，不拉伸、不裁切。真实 Core 比例矩阵与真实调度的比例失败场景通过；异常空图/NaN/批次回归拒绝，保持 PENDING。图像质量/真实模型构图仍未验证。 |
| G | CONFIRMED（技术摘要实际进入 Prompt）；画质影响 UNVERIFIED。原 Recipe→实际 multipart Prompt 可见 Processing configuration 摘要，含配置/凭据指纹衍生的摘要，未发现明文 Key。 | 自然 Prompt 仅去人物原文；请求身份用完整 SHA256 转 INT 连接传递。真实 hidden PROMPT 执行证实 256-bit nonce 可用，Z-only 参数改动 API POST 不增加。无真实模型证据，不声称画质已改善。 |
| H | CONDITIONAL，RH 现场 UNVERIFIED。routes.authorize 远端/代理须 token、Origin 检查、可禁用管理；前端 token 内存保存、密钥不入工作流、服务器 Key 不回读。管理员配置 HTTPS 内部主机仍可访问，插件不是租户网络沙箱。 | 拒绝无证据删除管理接口或改变合法网关合同。RH 须秘密管理、每租户独立进程/config/runtime/权限、持久存储和出口访问控制。鉴权/并发/持久账本回归通过不等于 RH 验收。 |

## 第二轮主动发现与修复

1. CONFIRMED：H3A2BackgroundFinish.run 缺 Guard 证据时先 attach_clean 写 READY 再报错。真实 Core 复现得到 READY；修复先验证 task、API evidence、PENDING 和 claim，再 attach_clean。相同探针修复后保留 PENDING，合法 READY lazy 复用/A→B→A 继续通过。
2. CONFIRMED：新增 authorize_snapshot 的初版在供应商条目缺失时直接 return，可被另一份配置/共享 runtime 利用。复审补充缺失供应商原凭据/退役原指纹校验；独立新 ConfigStore 用例阻断，原退役恢复回归保持通过。
3. 已解决升级兼容性风险：旧 Recipe 摘要去除会改变付费请求身份。未迁移/删除旧账本；若未找到请求且账本含无 identity_version=2 的已提交快照，返回 legacy_journal_new_request_requires_review。已有同 ID 仍走原恢复。管理员必须先查旧任务/费用，再决定为确实新的任务设置 H3_ADAPTER_ALLOW_LEGACY_NEW_REQUESTS=1；该开关仅解除新请求迁移门槛，不关闭幂等/凭据/哈希检查。不建议清空账本。
4. CONFIRMED（发布后独立 clone 复核）：未锚定的 CHANGELOG.md 属性也命中 docs/CHANGELOG.md，而历史 Git blob 为 CRLF，未编辑工作区也显示修改。仅将该规则锚定到 /CHANGELOG.md，保留历史文档字节；Python/六源码 pin/节点/工作流完全不变。重新生成 manifest/ZIP，再独立 clone 核对洁净状态。
5. 拒绝无证据改动：近似比例容忍/自动裁切、失败造空白图、自动重新付费、把不同用户共享文件系统当成插件可提供的租户安全、对主备状态机进行无关重构。未证实问题不计为新 Bug。

## 实际免费验证与替身范围

- Python unittest discovery：192 执行、192 通过、0 失败/错误/跳过。含原 180 项及 12 项独立取证回归；核心 Engine/Protocol/Config/SQLite 实现没有被替换。外部供应商使用 MockTransport 或真实 localhost HTTP。
- 原前端 6 套 JS 回归全部通过；web/h3_adapter.js 与基线字节一致，两个手动入口不变。本轮 JS 测试使用既有前端测试 DOM/API 夹具；不是 RH 浏览器实测。
- 真实 localhost TCP 协议回归 27/27 通过：幂等、主备、安全/不确定拒绝、并发、mask、任务 GET 恢复、终态失败、模型目录等。
- 官方 ComfyUI loader：八节点、路由、六源文件精确校验、篡改拒绝、实际 CPU IMAGE、有/无 MASK、Save/Preview 成功、2 次 Mock POST 与缓存重放通过。
- 真实 H3 Background Core + Bridge + Adapter：11/11 用例通过，含 Finish 顺序回归。
- 官方 ComfyUI 实际执行器：22 场景满足预期，6 正常成功、16 预期失败/阻断、0 跳过；17 次 localhost Mock POST，收费 POST=0。A→B→A、多窗、不同视角、Recipe 0.86→0.50、Z 失败恢复、异步 GET、比例拒绝、5 个独立标准消费者失败均覆盖。Qwen/Z 是明确的 CPU 替身；H3 输入是边界观察器，检查 124 帧/22 重叠/102 步长，未运行真实神经模型、完整 EasyUse 循环或正式 H3 MP4。
- 集成 JSON 的 nodes/links 原样 121/251；只更新 extra.integrated_repository 版本/六源码哈希。原 H3/Z 文件与原候选 114 文件保护清单复核无改动。
- 发布包按明确文件白名单构建，活动配置/Key/账本/临时文件不打包；Git blob、ZIP manifest 和六源码哈希须发布时再次逐项核对。

RH、真实收费 API、模型去人物画质与完整生产视频均未验证。实际 GitHub commit/网络/认证/推送/重新 clone 验收只以交付报告为准，不能由以上本地 PASS 推断。
