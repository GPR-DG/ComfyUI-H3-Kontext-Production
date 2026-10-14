# 第四轮独立源码取证：0.1.2 → 0.1.3

日期：2026-10-10；范围：`C:\path\h3-adapter`。本轮未调用收费 API、未使用真实 Key、未推送远程、未修改 H3 / Z-Image / Background Core。0.1.2 原版与此前审计意见均不是正确性前提。

## 1. 方法、原件与证据

先完整读取 `用户指定的 Skill 根目录` 中全局看代码逻辑、调Bug、省代码总规则、联网资料过滤器及关联审查/TDD技能。直接阅读全文：全部生产 Python、前端 JS、四家配置与协议变体、调度/任务状态机、测试、安装/打包脚本及正式 ZIP；旧报告只作线索。独立分工取证凭据、健康归因、发行，再由另一审核员复核最终实际 diff 与恢复链。

修改前保存 **72 个原文件**到项目 `audit-round4/before`，逐文件 SHA256 在 `ORIGINAL-HASHES.json`；没有备份或读出真实私密 Key。原发行 0.1.2：176205 字节、59 ZIP entries，SHA256 `469c24675b2ded9848e8b60c0b793ec5bad275342704b8d1d65ab3e0e74616b1`。原 ZIP 58 个 manifest 文件逐一与源码比对一致，Python AST 可解析、默认配置全部禁用、没有秘密/运行数据文件。**“原包与源码不一致、已经泄密、存在语法错误”没有证据，REJECTED；不能从缺少忽略规则推断已经泄露。**

原版全套：117 项，116 通过、1 Torch skip；原前端合同及 15 项 review、6 个 round3 场景通过。这只是基线，未用通过数量排除漏洞。新增测试先在原件/未修复代码上 RED，再对同一测试 GREEN；还用真实 loopback HTTP / aiohttp 管理路由 / SQLite 和真实本地 Git clone 独立复现。

原始记录均在项目 `audit-round4`：`credentials/REPORT.md`、`health/REPORT.md`、`release/REPORT.md`、`final-review/REPORT.md`、各 RED/GREEN/probe JSON/log。最终文件差异和前后哈希见 `CHANGES.json` / `CHANGES.patch`；发行/原件复验见 `package-verification.json`。插件 ZIP 内不包含整个审计临时树。

## 2. 问题一：网址变更、Key 与供应商身份

### REJECTED：同 ID、同 Key，仅明确修改 Base URL 必须自动清 Key

**旧 Key 确实会发到用户新配置的地址**，这是配置式网关迁移合同允许的行为，不是“检测到 URL 变化就必须清 Key”的既定业务要求。管理员可显式配置地址和 Key，没有域名绑定承诺。对所有 URL 变更清 Key 会破坏同网关地址迁移及旧任务恢复，本轮拒绝此类修改。新任务按当前配置发送；旧受理任务按原快照 URL 查询。`test_saved_key_allows_old_url_after_address_change` 及独立 loopback 探针验证后者。用户必须确认目标是愿意接收此凭据的服务器。

### CONFIRMED C1 / C3：新增供应商意外继承他人凭据（P1）

原前端按现有 ID 计数新增 `provider_1`，同时自动填 `H3_PROVIDER_1_KEY`；发行 primary 本来就使用这个环境变量。`ConfigStore.key` 环境优先于私密文件，所以给新商保存 B Key 仍可能实际向 B 发 A Key。删供应商保留秘密是为恢复旧任务，但新增按钮复用被删 ID，又会继承其私密 Key。实际运行原 JS 回调及 loopback 假 Key 抓包重现，不是单凭命名猜测。

最小修复：`web/h3_adapter.js:155-159` 新 ID 使用时间戳+随机后缀、检查当前 ID，`key_env` 留空，新商仍默认禁用。**不删除旧 Key/账本**。手工复用 ID/环境变量仍是明确的凭据共享，不宣称阻止管理员主动误配置；随机 ID 不是密码或绝对全局唯一证明。

### CONFIRMED C2：旧任务 URL 配合当前另一商家的 Key（P1）

原 `Engine._recover` 用原 provider 快照 A 的 URL，却通过可变 ID 获取当前 Key B；环境 A 已移除还会回落到该 ID 的 B 私密 Key。接受任务后同 ID 改为另一商家并更新 Key，即可对 A 发 B 凭据。新提交的资格检查与实际工厂两次读 Key、模型发现的旧配置与新 Key，也存在同类竞态。独立抓包：原 POST A 仅一次，恢复 GET A 却携带 B；不是再次收费，但凭据隔离确有缺陷。

修复定位：`config.py:198-218` 的 `credential_identity` / `credential` 在原有设置锁内检查身份并一次捕获 Key；`engine.py:127,143,152` 用同一捕获值提交、私密快照增加 SHA256 凭据指纹；`routes.py:82` 模型发现同样使用一致性读取。**不保存明文 Key，不改变请求 fingerprint、nonce、SQLite schema。**

恢复规则（`engine.py:197-200,251-252`）：当前身份相同可同站轮换 Key；身份变化但捕获的原 Key 指纹仍匹配，也可查询原快照 URL；两者均不满足则 `awaiting_result / credential_changed_no_resubmit`，不发 HTTP、不释放预留、不删除 task_id、不换备用付费。恢复原 Key/配置后，同 nonce 继续旧任务，整个修复后 loopback 链仍仅 1 POST。

**迁移边界：** 0.1.2 遗留快照没有凭据指纹。相同身份轮换可恢复；已删除/改变身份不能证明原 Key，需还原原 provider 条目及 Key。这是保守隔离的操作约束，不得新 nonce/删账本绕过。已完成缓存不依赖 Key。

### CONFIRMED C4：配置 CAS 不保护旧窗口写 Key（P2）

原配置旧 revision 返回 409，但旧窗口 Key POST 没有 revision，仍 200 并覆盖同 ID 新商的 Key；未应用身份表单/未保存 JSON 也能先写 Key。修复 `config.py:220-234` / `routes.py:62-70`：锁内检查当前成员及可选 revision，冲突 409；前端 `:194-220` 携带 displayed revision、阻止未应用身份/未保存 JSON，异步配置保存记录**点击时快照**，不把等待期间的编辑伪装成已保存。

兼容的直接脚本仍允许省略 revision：含义是写**当前** ID，不是旧窗口并发安全保证；并发管理应带 GET 的 revision。节点端口不变。

证据：`test_round4_credentials.py` 15 项（旧 URL、同站轮换、遗留/删除身份、环境回落、单次捕获、发现竞态、Key CAS）；`test_round4_frontend.mjs` 6 场景；`credentials` 原件 RED 与修复后的独立 loopback/aiohttp JSON。供参考的 [OpenAI 官方 SDK 客户端源码](https://github.com/openai/openai-python/blob/main/src/openai/_client.py) 允许分别设置地址和 Key，但本结论来自本项目明确合同，而非社区做法替代业务判断。

## 3. 问题二：客户端错误与供应商健康

### CONFIRMED H1：安全切换判据被误用作供应商故障判据（P2）

原调用链：`Engine.edit` reserve / submitting → `Protocol.submit` 本地模板校验或 `_headers` 本地鉴权校验 → `APIError(safe_to_failover=True)` → release **同时 cooldown**。7 种本地错误均 primary 零 HTTP，却记健康冷却；修正模板/Key、新 nonce 仍跳过 0.1 主家去 0.7 备用；有限费用上限也可能被错误挡住。PoolTimeout 是本地连接池等待，同样被冷却。真实 loopback 与 MockTransport 两种独立探针一致。

修复：`APIError`（`protocol.py:14-18`）分离 `provider_failure=False`；仅明确、配置允许的远端拒绝（`:114`）及 ConnectError/ConnectTimeout（`:128-129`）标供应商路由故障；PoolTimeout、本地模板/鉴权/预算/期限不标记。`engine.py:169-173` 仍按 safe 判据释放/切换，只按 provider_failure 冷却。已知真正连接失败仍冷却；远端 401 说明当前凭据路线不可用，允许配置的安全拒绝仍冷却。

**REJECTED：** “所有确定未发出的失败均不可切换”不成立；可切换到有效备用是正常功能。也不移除所有冷却。**读/写超时、5xx、结果缺失、受理后错误不能据此重付备用**，这些 unknown/accepted 分支完全保留。

证据：`test_round4_health.py` 5 项，原 RED 有 8 个断言失败；GREEN + 14/15 case 独立 Mock/HTTP 探针，包括修正配置后主家重新使用、真实 refused connection、远端拒绝预算释放、uncertain/accepted 不重付。成熟实现也分离客户端/编排错误和后端健康，但判断来自本项目零 POST/SQLite/费用事实，参考 [LiteLLM cooldown 源码](https://github.com/BerriAI/litellm/blob/main/litellm/router_utils/cooldown_handlers.py)、[HTTPX transport 重试边界](https://www.python-httpx.org/advanced/transports/)；没有增加自动 POST 重试。

## 4. 问题三：GitHub 与安装完整性

### CONFIRMED R1：源码安装缺初始化步骤（P2，发布文档缺陷）

`.gitignore` 正确排除了个人 `config/providers.json`，Git clone / GitHub Source ZIP 因而没有此文件；`ConfigStore.load` 不自动创建，前端先 GET config 失败就无法进入管理。原 README 只说发行 ZIP 配置已存在。实际本地 Git clone 插件注册成功、4 routes 存在，但 GET 400；复制 example 后 GET 200、四商禁用且 keys=false，Engine no_provider、零外部 POST。

修复 README 源码首次初始化的 Windows / POSIX 命令，**存在则不覆盖**，重启前执行；再次运行对人工配置不覆盖已验证。保留 active config 忽略，不加隐藏 bootstrap。Release ZIP 与 GitHub Source ZIP 分开说明。

### CONFIRMED R2：Git 秘密文件忽略不完整（P2，发布防护缺口）

原 `.gitignore` 不排除 `.env`、`.env.production`、`private.env`，实际 `git add` 可跟踪合成秘密文件；原 ZIP builder 已排除，并没有证明真实 Key 泄露。本轮对齐忽略规则并补 whole runtime.private / SQLite 伴随文件；真实 Git staging 回归验证。忽略不能清除已追踪文件、不能抵挡 force-add；自定义 config/runtime 路径要单独隔离。[Git 官方说明](https://git-scm.com/docs/gitignore) 支持此边界。

**REJECTED：** 原正式 ZIP 依赖漏包/秘密数据误打包/源码不一致/语法坏掉未成立。HTTPX/Pillow 明确声明，NumPy/Torch/aiohttp 使用 ComfyUI 自带依赖；开发依赖另列。MIT 与依赖许可证原文附带；没有捆绑 GPU 框架或第三方私密程序。实际官方 loader 合同及 [ComfyUI 手工安装文档](https://docs.comfy.org/installation/install_custom_node) 与插件根 `__init__.py` / `WEB_DIRECTORY` / 映射一致。

**发布结论：** 可发布私有或公开**开发仓库**，仓库根须是 `ComfyUI-H3-Adapter`，不是包含 venv/研究快照/审计临时树的整个桌面交付目录。首次初始化不可省略；发布前检查既有跟踪记录/自定义路径。没有实际 GitHub push，也未声称已经发布。正式 ZIP 字节/manifest/默认配置及解压回归由本轮独立证据核验，见项目 `package-verification.json` 与 `release/FINAL-RELEASE.md`。

## 5. 隐藏问题与修复过程中独立抓到的回归

### CONFIRMED G1：非对象 JSON parameters 被悄悄当成空参数（P2）

原 `isinstance(params or {}, dict)` 把 `[]`、`false`、`0`、`""` 当 `{}`，实际 Engine/Protocol POST 成功，而输入合同要求 JSON 对象。根审独立新测试 4 子例 RED；最小改 `engine.py:60` 检查非 None 非 dict，在 fingerprint/claim/HTTP 前拒绝。None 和 `{}` 保持默认兼容，`test_round4_parameters.py` 两项 GREEN。不替用户猜参数语义。

### CONFIRMED 本轮中间修复回归，交付前已纠正

最初凭据隔离 guard 误挡已落盘 inline base64 的 result_ready；根审 RED 和新独立审核员原版/中间版探针均证实原版成功、中间版 awaiting、0 HTTP。它不是原 0.1.2 的缺陷，不能隐瞒为“旧 Bug”。匿名 URL 和不向 CDN 发 Key 的下载同理不应要求旧 Key。

最小修复共享 `Protocol.result_requires_key`（`:238-242`），同时用于实际结果 headers（`:268`）和恢复（`engine.py:197-200`）。本地内联、显式不认证 URL、跨 origin CDN 不需凭据仍可恢复；**同 origin 且 download_auth=true 仍检查原凭据**。原 URL allowlist、端口/origin判断、TLS、禁止 redirects 不变。`test_round4_recovery.py` 2 项含 3 RED 子例及认证控制组 GREEN，旧 4 个下载边界及独立零 HTTP 恢复探针通过。

## 6. 全链复核：不该修的设计与仍待验证

| 范围 | 判断 / 证据与边界 |
|---|---|
| 模型选择误固定商家 | REJECTED；picker 保持 auto，只显式操作才固定；15 个前端 review 场景仍通过。别名用于逐商模型 ID 映射。 |
| 模型变化能力/价格残留 | REJECTED 当前已知路径；changed ID 清 capabilities/defaults/报价并提示再确认，same ID 保留明确配置。发现 ID 列表不是能力或报价。 |
| JSON Template 声称 MASK 但不传 | 当前 0.1.2 已有真实 token 消费/上传前校验；18 个 round3 模板回归及 MASK 备用全链重跑。任意供应商实际 MASK 语义仍 UNVERIFIED，不假定 API 接收等于执行语义。 |
| 同 nonce 换实际模型仍旧缓存 | 正常防重付设计；fingerprint 不含可变商家实际模型，稳定 alias+输入+nonce 是原付费意图。恢复旧任务不能换模型重付；新任务显式新 nonce。拒绝改变 ID 算法或清缓存。 |
| 同 nonce 并发/超时/受理 | 原 journal、claim、预算、终态保护不改；同 runtime 跨进程一次 POST、迟到轮询不覆盖 completed、unknown 不备用、accepted 仅 GET 回归通过。不同容器不共享账本不受此保证。 |
| 图像尺寸/原背景保护 | 真实输出尺寸保留，不默默 resize；MASK 是向外部模型发送编辑意图，不保证像素级未遮挡区恒等。硬合成/背景结构质检属未来背景修复业务模块，拒绝擅加功能。 |
| 协议可更换 | JSON/multipart、按需上传、base64/URL结果、GET异步、配置正式模型发现/手填/映射已模拟验证；并非任意 HMAC/gRPC/WebSocket/私有账单协议自动兼容，不写死 SubRouter。真实商业协议未接通不等于源码 Bug。 |
| 费用 | 用户保守估计、同账本预留，不是供应商账单硬上限；未知/零价/币种历史回归通过。供应商上传是否计费、safe rejection 是否真的未计费需正式合同。 |
| Key/日志/工作流 | 无 Key widget、不回显秘密、不把原始第三方异常/body作为报告；假 Key 抓包与输出检查。运行目录和密钥仍要求 OS/平台账户隔离，不是加密保险库。 |
| 语法/发行 | AST 和前端 module syntax 实验，没有发现已证实语法 Bug；此前源码/ZIP一致。具体当前文件数、SHA和包运行结果以最终原始记录为准。 |

## 7. 验证结果与异常如实保留

最终源码**两次串行**全套：每次 **143 tests，142 pass / 1 skipped / 0 failure / 0 error**（15.389s、14.687s），日志 `final-source-unittest-1.log` / `-2.log`。四套前端：基础合同、15 review、6 round3、6 round4 全通过；AST/JS语法记录 `source-syntax.json`。正式 ZIP 独立解压运行同业务链的记录为 `package-unittest.log` 及四套 `package-*.log`，最终结果汇总在 `package-verification.json` / DELIVERY，不能以源码测试替代包测试。

**唯一 skipped**：真实 Torch BHWC tensor 端口。使用 NumPy double /真实 PNG /本地 HTTP 不等于完整 ComfyUI UI 执行。独立最终审核再跑 25 targeted、15 core、22 恢复/下载/凭据组合与自有探针，未发现剩余已证实回归；不是生产认证。

**没有抹去的异常：**
- 两次磁盘满中断，日志保留；只清理本项目可重建的公共 ComfyUI clone/venv bytecode，没有改其他目录，见 `SPACE-INCIDENT.txt`。盘满不是协议失败证据。
- 两个独立 targeted 组合先观察到 Windows `atomic_json → os.replace secrets.private.json` 的 WinError5；最终审核同 22 项重新全通过、受影响项另三次通过，根审全套两次无错。完整首次 traceback 在 `release/independent-health-params-review.log` 和 `final-review/final-recovery-green.log`（后者历史文件名不代表首次 green）。**根因 UNVERIFIED**：仍不能确定是外部占用/文件系统还是程序竞争；未加盲目 sleep/retry/异常吞掉。目标环境需重复并发写配置/Key和占用测试，不能把偶然通过当稳定性证明。
- 个别探针首次命令类名错误/编码问题等原日志与修正命令均保留，不当源码 Bug。AnySearch 本轮 CLI 因缺 requests 无法启动，使用官方原始资料替代；未读取/使用真实搜索密钥。

## 8. 可测试、GitHub、RH 与生产分开评价

1. **普通 ComfyUI：可进入受控免费 mock 实测**，不是已经实机通过。用 ComfyUI 自己 Python 安装依赖、源码安装先初始化；LoadImage → H3ImageEdit → SaveImage，验证 object_info、history、标准 tensor、成功/失败空 IMAGE、前端修改/模型发现/管理 CAS、原 nonce 恢复。
2. **GitHub：具备开发仓库提交/安装条件**（正确根目录、初始模板说明、忽略、许可证、测试、发行manifest齐备），不意味着真实商家/RH认证或生产版本；本轮没有远程推送。
3. **真实商家：UNVERIFIED。** 需其正式编辑/上传/异步/结果/发现文档、真实模型能力、实际费用/受理/幂等合同，以及明确授权测试 Key/收费额度。不能猜 SubRouter 接口或声称去真人效果已验证。
4. **大陆 RH：UNVERIFIED，非生产就绪。** 分别要确认节点库收录、允许部署自定义节点、前端/管理route加载、目标 API/CDN HTTPS及鉴权外连、服务器秘密保存和租户隔离、持久共享 runtime /多副本一致性、实际任务完成及 IMAGE 输出。普通 ComfyUI 兼容/公开安装资料不能证明以上任何一项；必要时经授权用外部 Gateway，但本轮不擅加服务。
5. **生产：未达到。** 除上述实机/商业协议/RH条件外，还需 Windows 写配置异常根因与目标环境稳定性、持久卷故障/备份恢复、供应商账单硬限制、并发中断恢复/真实大图资源与质量验收。不要用删除账本/自动新 nonce 解决卡住任务。

## 9. 修改边界与交接

必要生产变化限 ConfigStore、Engine、Protocol、routes、单个前端、Git忽略；新增针对性测试与必要安装/审计说明，版本 0.1.3 / builder evidence / manifest /发行ZIP/交付记录同步。`nodes.py`、`__init__.py`、`ledger.py`、请求 fingerprint/nonce 算法、模型/协议模板、示例 workflow、旧测试、依赖及许可证无业务改动，哈希差异可查。拒绝域名强绑定/清秘密/重构调度器/额外背景合成/为了测试增加等待/自动付费重试。

后续 Agent 先读本报告及 README，再看 `audit-round4` 的原件、RED/GREEN、真实 probe、完整源码与解压包日志；在同 runtime 保留账本、原 nonce 与 provider快照，先完成免费的真实 ComfyUI 验收，再经用户明确授权决定商业 API / RH 实机。完成本轮后停止，等待指令。
