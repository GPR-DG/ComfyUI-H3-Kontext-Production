> 当前版本 0.1.7（2026-10-13）的独立结论和实际测试见 [AUDIT-017](docs/AUDIT-017.md)。下文保留历史记录，其中旧版本“未修复”说明不代表本版；GitHub/RH 状态以实际交付报告为准。

# 本次增量复核：2026-10-12，开发测试候选

此节是当前结论，后面的 2026-10-11 报告仅作为历史记录。基线 main：`3d5aa47a6d7528da8a6cc9004c590635f2de37db`。远端与本地基线逐文件核对；没有整库覆盖、改名、接口变更或调度重写。源码判定与实际探针结果共同构成本节证据，旧 PASS 不用于认证本次代码。

## CONFIRMED 与本次修复

| 标记 | 文件/可达条件 | 最小修复与验证 |
|---|---|---|
| IA04 | routes.py 直接 compare_digest(str,str)，非 ASCII token 可触发异常；前端 fetch 失败或第二次拒绝后留下坏缓存 | UTF-8 bytes 比较并拒绝无效编码；清除本次请求对应的坏缓存，保留拒绝信息。实际 aiohttp 与 Chromium 验证 Latin1、中文、正确/错误/缺失 ASCII 和后续重授权 |
| IA05 | 同一管理窗口允许重叠密钥保存/删除，迟到回包可能覆盖新状态 | 保存按钮串行 guard、disabled/finally 与关闭窗口回包保护。真实路由先落盘再延迟回包；有/无环境 Key 的连续保存/删除均匹配服务端；原供应商切换回归保持通过 |
| IA06 | 配置 POST 成功后，用户把编辑器改成无效 JSON，fill 错误覆盖保存成功 | 成功后保留 revision、刷新 Key 状态，分别提示刷新失败和未保存编辑错误。浏览器同时检查服务端落盘与原编辑文本 |
| IA11 | 结果 temp.replace 失败后留下临时文件 | 写入/替换加 finally 清理；Windows 只读目标探针：旧目标保留、temp=0、任务 result_ready、预留费用 0.1；恢复 completed，总 POST=1 |

## CONFIRMED：稳定发布阻断，尚未修改

- IA01：protocol.py 的 iter_bytes 在 cap 检查前解压。新真实 TCP 探针中 65,536 bytes 上限下，gzip/deflate/多重编码先产生 4,194,304 bytes 解压块，随后 response_too_large。连接已释放。此前另一次 1 KiB/8 MiB 核对属于不同探针，不能混作本轮参数。未证明生产 OOM。
- IA02：nodes.py 对失败、未知、等待、阻断和无供应商返回空 IMAGE。本轮实际官方 ComfyUI PromptExecutor 与 PyTorch 下，成功有/无 MASK 的 SaveImage/PreviewImage 可以消费；五类无图状态触发标准消费者 IndexError。成功路径通过不能代表失败路径通过。

## REJECTED / 不适用于当前基线

- IA09 候选的 REQUIRED_FILES 夹具变更：当前 builder 没有这个属性，不能移植不存在的接口。保留现有 RELEASE_FILES，只增加本次必要回归文件。
- IA10 候选的 begin_task 夹具变更：当前 Journal 使用 begin，不存在 begin_task。没有证据需要该夹具修改。
- “整份候选替换当前仓库即可保留保护”：源码反证；候选会丢失 health.identity 和参数切换清理，已拒绝整文件替换。
- 本轮同一持久账本、相同 nonce 的 Mock 请求没有新增重复 POST 或预算突破；这不是对所有商家收费的证明。

## 保留的现有保护

锁内捕获配置 revision；credential_generation 隔离删除重建任务；连续身份 Key 轮换恢复；health.identity 冷却与旧表迁移；真正切换 provider/auto/model ID/alias 清空 parameters；选择不变保留参数。config.py、ledger.py、nodes.py、protocol.py 未修改，原身份/前端回归与宿主验证脚本均保留。

## 本轮实际验证

| 验证 | 当前合并版本结果与边界 |
|---|---|
| Python | discovered=174，run=171，pass=171，failure=0，error=0，skip=0，excluded=3；新增 1 项授权回归，原断言未改 |
| JS | 5 套原有 suite + 1 套新 suite 全部退出 0；新增 4 类 token/编辑器/并发场景 |
| 独立 HTTP Mock | 27 类真实 loopback TCP 场景通过：协议 payload、主备、未知不换家、重复、并发、预算、恢复和配置身份 |
| Chromium/生产管理路由 | 9 组探针记录；令牌重授权、保存成功后无效编辑、有/无环境 Key 的串行保存/删除符合合同；中文 token 的浏览器 ByteString 拒绝如实保留 |
| Windows 文件探针 | replace 失败后 temp=0，旧目标保留，恢复无重复提交；不是所有 ACL/外部锁环境验收 |
| 实际 ComfyUI CPU 宿主 | 导入、注册、路由、IMAGE/MASK、成功缓存和消费者通过；五类无图失败状态在实际执行器里仍触发消费者 IndexError |
| HTTP 解码/截止时间 | cap 之前的大块解码缺陷仍在；提交超时/断流保留 uncertain/费用，不重复 POST。截止时间存在小幅超时，不宣称硬实时 |

明确排除既有 Git 写入夹具（未修改测试来掩盖排除）：

- test_round4_release.PublicationTests.test_documented_source_initialization_creates_only_missing_config
- test_round4_release.PublicationTests.test_git_add_does_not_track_credential_or_runtime_files
- test_round5_release.ReleaseBoundaryTests.test_git_ignore_covers_nonstandard_config_backups

独立宿主、浏览器与文件系统探针原始证据保留在本次本地交付，未把含私人路径的日志上传。新增可公开回归文件随源码发布；打包重新生成 manifest，并检查成员、CRC 与每个成员 hash。

## 未验证风险与最终判断

特殊 Linux 路径锁碰撞、数据库长锁等待、硬退出残留及所有目标文件系统环境未完成验收。真实供应商的接受/拒绝语义、收费、编辑质量、RH 部署和跨版本兼容仍未验收。费用是保守配置估计，不能视为商家账单。

A：业务需求部分达到；多供应商、主备、去重和恢复的本地验证成立，生产闭环未完全达到。
B：允许增量上传 GitHub 作为开发测试候选；上传操作后独立核对远端完整 SHA，执行结果在交付回复中报告。
C：仍需修复 IA01/IA02 才能重新考虑稳定发布。Stable Release：NO；本轮不创建稳定标签或 Release。用户指定的 commit 标题含 stable，不代表稳定验收通过，commit 正文会明确 Development candidate; Stable Release NO。

---

# 以下为历史报告（2026-10-11，不代表当前发布结论）

# FINAL_AUDIT_REPORT

审计对象：ComfyUI-H3-Adapter 0.1.5。日期：2026-10-11，Asia/Shanghai。方法：独立逐文件取证、直接执行生产回调与网络捕获、先复现后最小修复；不根据历史报告、旧 PASS 或测试数量判断正确。

## 结论

A. 本地 ComfyUI IMAGE/MASK → 配置化外部图像 API → IMAGE 的代码与 Mock 闭环满足所列业务设计要求，包括自填 URL、多供应商、主备、安全失败切换、共享持久化防重及恢复；节点名和接口合同保持不变。支持未来 RH 接入的前提已明确，**不能据此宣布 RH 或任何真实商业供应商已接通**。

B. 经过源码、暂存文件与精确白名单 ZIP 审查后，可公开上传 GitHub。本报告确认的是公开源码与本地验证门禁，不预先宣称远端 push 成功；发布操作最终以远端 HEAD 与本地提交比对为准。真实 Key/个人路径/私密 runtime 不属于发行内容。

C. 本次确认的四类代码问题均已修复，原测试未修改。未再定位到需要修改的可复现业务缺陷；仍有未验证的外部商家、RH、目标环境文件锁/ACL、真实计费和效果风险。一次实际 WinError 5 失败没有被成功重跑抹去，不能承诺所有部署环境的文件替换可靠性。

## 已确认问题与最小修复

| 编号/状态 | 源码证据与实际复现 | 修复及边界 |
|---|---|---|
| F1 CONFIRMED | ConfigStore.load 与 credential 两把锁之间可删除/同 ID 重建、或修改模型和 Key；原同 URL/认证身份检查允许旧配置借新 Key。模型发现同样可错配。新增回归先捕获到错误 POST/发现调用。 | load 返回兼容 dict 的私有 snapshot，锁内附加非序列化 revision；提交/发现 credential 核验读取时 revision，变更则发网前拒绝。没有改公开配置 JSON。 |
| F2 CONFIRMED | accepted 环境 Key A 任务，删除、同 ID 同 URL/key_env 重建并改成 B，same 身份条件允许拿 B 恢复 A；旧 env Key 不在 retired 列表。新增恢复回归先失败。 | snapshot 加非秘密 credential_generation；不同代际只有匹配旧 fingerprint 的 active/retired Key 可恢复；同一连续身份仍允许正常 Key 轮换；旧快照无代际按 0 保守处理。 |
| F3 CONFIRMED | health 只以 provider ID 冷却；401 后删建同 ID，合法新供应商被旧冷却跳过。新增真实 Engine/MockTransport 回归先返回 no_provider。 | health 增加可空 identity，Engine 传地址/认证身份/代际；新身份不继承旧冷却；旧 schema 原子迁移、原任务不丢。历史无 identity 冷却保守保留至过期，最长配置冷却时间。 |
| F4 CONFIRMED | web/h3_adapter.js 只更新 provider/model_alias，没有清空节点 parameters；旧 size 留到新供应商或模型。新增真实回调 6 场景中修复前 4 个失败。 | 实际切换 provider/auto、模型 ID 或 alias 时 parameters 清为 {}；选择未变保留显式参数。已有新 ID 清理能力/价格/defaults 的逻辑保持。 |

生产改动限定在 config.py、engine.py、ledger.py、routes.py、web/h3_adapter.js；另增验证代码，更新构建白名单及公开文档。未重写架构、调度或工作流。

## 六项历史风险的重新判定

| 问题 | 判定 | 当前源码理由 |
|---|---|---|
| 1 删除、新建、ID 复用的 Key/revision/任务/cache | CONFIRMED（F1/F2/F3），已修复 | 原 save 会 retired Key/递增 generation，revision 已包含代际，旧窗口 ABA 已被阻止；但提交/发现读竞态、环境 Key 恢复和冷却仍有实际漏洞。本轮补齐。completed 缓存按完整输入/nonce恢复原任务，是合同，不因配置变化新扣费。 |
| 2 已扣费/未知任务又提交备用 | REJECTED | reserve 在 POST 前提交 submitting；submitting/uncertain 不 POST；accepted/result_ready 只恢复原快照；failed 终态不重开任务。仅未发出或配置明确的非受理 4xx 才 reject 为 ready 并切换。读写超时/5xx/损坏成功响应均停止备用。 |
| 3 配置临时文件 Key 泄露 | REJECTED（所述残留漏洞） | atomic_json 的 try/finally 统一 unlink，私密文件写数据前 chmod，fsync 后 replace；异常回归覆盖失败清理。Windows chmod 不提供完整 ACL 隔离；崩溃/外部句柄和磁盘恢复不在此保证内。 |
| 4 IMAGE/MASK/multipart/JSON/header/model/prompt 未真实发送 | REJECTED（所述系统性未发送） | submit 实际组 files/data/JSON token 与 auth header；网络捕获验证真实字段。IMAGE/MASK 模板未映射在发网前拒绝。JSON 常量 model/prompt 是明确允许的合同，缺 token 的映射报告 warning，不能说节点输入一定改变这种常量模板。 |
| 5 切换继承旧 model/size/mask/pricing | CONFIRMED（仅 F4 参数残留），已修复 | 模型能力/价格/defaults 本来按各家 mapping 读取，新 ID 本来就重置为保守未知配置；问题仅在节点 parameters。供应商切换和模型/alias切换现在清空，原默认值与报价回归保留。 |
| 6 ComfyUI 输入输出不符合规范 | REJECTED | 注册 H3ImageEdit；IMAGE 输入、可选 MASK，IMAGE/STRING/STRING 输出，真实 float BHWC。官方宿主 load_custom_node 和 SaveImage/PreviewImage 消费验证成功。失败会给占位 IMAGE 与明确 report，用户必须查看 report 判定成功。 |

## 全局业务复核

- 并发/数据竞争：SQLite 唯一请求 ID、BEGIN IMMEDIATE claim/预算预留；并发请求只有一个编辑 POST。mark 限制合法源状态，迟到轮询不回退 completed/failed。重复 GET 可发生，不重复付费 POST。
- 配置覆盖：settings_lock 跨进程序列化，管理保存支持 expected_revision；服务端 API 未传 revision 的显式覆盖仍是现有合同。提交/发现的新检查阻止已读取旧配置继续借新凭据。
- 调度/fallback：手选或关闭自动切换不换家；Mask/多图能力/参数/成本筛选在调用前；本地模板/认证错误不错误冷却服务商；未知受理不释放预算、不换家。
- 费用：price_upper_bound 是手工配置的每请求估计。未知费用在有限预算下拒绝；接受/未知/成功保留预留，明确拒绝释放；币种不混算。不是实际账单，也无法替商家强制真实扣费上限。
- 秘密与网络：Key 不在节点端口、工作流、public config、任务快照明文或返回报告；指纹不等于密钥保险库。管理默认限制本机/同源，远程需 token 或禁用。结果 URL 认证按主机边界，限制响应/图片体积；管理员仍控制配置 URL、Header 与协议声明。
- 异常：节点和 Engine 用稳定错误码避免把厂商响应/Key 回显；广义异常会降低诊断细节，但未知提交仍冻结，未吞异常后再提交备用。
- 缓存/恢复：真实模型/供应商/费用随原任务快照；已完成缓存缺失拒绝重投。修改配置不是新付费意图，nonce 才是显式新请求。result_ready 使用持久结果定位恢复；未把带凭据的完整响应公开。
- 公开发行：.gitignore 与精确发行白名单排除 active config、私密 Key、DB、缓存、备份和日志。Git 暂存逐文件检查与 ZIP 哈希复核同样必要；单靠 ignore/白名单不能发现已列文件中被人为写入的秘密。

## 最终验证

执行入口与依赖准备见 docs/TESTING.md。保留原测试不改；新增回归先在待修实现失败。以下结果以最终执行完成后的验证记录为准。

| 验证 | 结果与实际覆盖 |
|---|---|
| Python unittest | 173 项，全部通过、无 skip；含配置保存/失败清理、重复请求、并发、safe failover、unknown 不换家、异步恢复、费用、协议及新身份回归 |
| JS | 5 个 MJS suite 全部通过；新增 6 个真实生产回调场景，含切换清参数及未变化保留 |
| 真实 TCP Mock | 27 类场景全部完成；捕获 multipart/JSON/header/Mask、主备 POST 次数、异步 GET、预算、模型发现/nonce |
| 官方 ComfyUI | load_custom_node/路由注册成功；CPU torch 有/无 MASK；两次编辑 POST；重放不增加 POST；SaveImage/PreviewImage 消费实际 IMAGE |
| ZIP | 精确白名单、manifest 每文件 SHA256、CRC、默认禁用配置、无 secrets/runtime/cache；解压副本独立 Python/JS/TCP/宿主验证 |
| Git | 暂存名单与变更审阅、diff --check；远端操作不以权限 scope 推测成功，push 后核对 HEAD |

验证环境：Python 3.12.14；HTTPX 0.28.1；Pillow 12.3.0；aiohttp 3.14.4；NumPy 2.5.2；PyTorch 2.14.1+cpu；Node 24.18.0；Git 2.54.0.windows.1。官方宿主固定 SHA：0df64eb242b7c5759c3e86afd5d1846d923b1033。本轮只验证已有宿主快照，未声称覆盖所有未来版本。运行时下限与锁定依赖范围按 pyproject.toml/requirements.txt；不同 Python/平台组合未全矩阵验证。

GitHub 实测：认证 HTTP 200，账户 GPR-DG；目标仓库初始为 404，已通过 GitHub API 创建公开 GPR-DG/ComfyUI-H3-Adapter（HTTP 201），随后查询实际 push 权限为 true。提交采用该账户 noreply 身份；远端结果在 push 后单独记录。

Git diff --cached --check 已完整审阅。保留的原文第三方许可 licenses/pillow-0-LICENSE 有历史行尾空白，docs/AUDIT-ROUND2.md 与未改的 tests/test_round3_state.py 有历史末尾空行；不修改第三方原文或旧测试来消除它们。排除这三份未改文件后全部暂存文件的 whitespace 检查通过。CRLF 按 Windows 原源码保留。

## 未验证风险与失败记录

1. **实际观察到 Windows 原子替换失败。** 一次 169 项全量运行中 secrets.private.json 的 os.replace 报 WinError 5；随后 171 项运行通过。保持原失败证据，不根据重跑推断根因或保证永久可靠。异常路径清理临时文件；部署前需验证磁盘/ACL/外部占用与文件锁，持久化可用性仍有风险。
2. 商家是否真将配置 safe_reject_statuses 视为“未受理”需要其正式合同。配置错误或商家违约不在本地算法保证内。
3. 未向 SubRouter/其他中转/RH/自建真实商家发起付费编辑，无法证明实际效果、报价、尺寸/Mask语义或真实账单。上传端点也须确认只是素材上传而非收费编辑。
4. RH 节点收录、安装、外连、密钥注入、租户隔离与持久卷未验证。不同进程必须共享同一 ledger；分离 runtime、多实例分库、删 DB、修改 nonce 均可产生新扣费。
5. Windows chmod 不建立完整用户 ACL；Secrets 与结果运行目录依赖部署者保护。Retired 私密 Key 为历史恢复保留，不保证用户删除供应商即抹除所有历史秘密；环境 Key 未保留时恢复保守阻止。
6. 本轮未做真实浏览器完整 ComfyUI 图形交互/E2E或网络 UI 负载测试；JS 在 Node VM 中直接执行生产回调，宿主为 CPU程序化验证。未进行 GPU/所有宿主版本矩阵。
7. 崩溃留下 submitting/uncertain 是安全停止，不能凭空恢复无 task_id 的商家任务。需人工核对原任务/账单；改变 nonce 是新付费请求，不能当作自动修复未知状态。

这些边界不应被“stable”提交文字、旧报告或测试通过抹去。
