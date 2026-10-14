# 第三轮独立源码审计：0.1.1 → 0.1.2

日期：2026-10-10（Asia/Shanghai）。结论依据本轮新读源码、原版抓包/账本、失败复现和修后回归，不以此前 Codex/GPT 报告或绿色测试作为正确性前提。外部报告全文未提供，本报告只裁决用户转述的具体命题，不冒充逐字核对完整外部报告。

**总体判断：有真实 Bug，已作必要局部修复；异步恢复测试失败不证明状态机故障；同一付费意图保留旧模型缓存是正确设计。可进入受控 ComfyUI 免费 mock 实测，不达到生产标准，也不是 RH 已部署。**

所有任务产物均在 `C:\path\h3-adapter`；只读 Skills 位于用户指定 D 盘。未修改 H3 主链、Background Core、Z-Image 原图；未调用收费 API、使用真实 Key、推送远程仓库。

## 1. 范围、证据及完整调用链

完整读取当前节点注册/张量转换、五个后端模块、前端、四类配置模板、全部 Python/JS 测试、mock server、构建脚本和正式 0.1.1 ZIP；对相关社区实现读取实际请求/重试/合成函数，未移植代码。完整读取指定四个 Skills 及关联调试/TDD/代码审查 Skill。AnySearch 配置缺失，匿名服务解析失败；取证回退到可用官方文档/源码和项目内固定快照，不使用搜索密钥或收费服务。

源码根为 `C:\path\h3-adapter\ComfyUI-H3-Adapter`。以下相对路径均相对此根；“原版行号”指 `audit-round3\before\ComfyUI-H3-Adapter` 中未改 0.1.1。

执行路径：
1. `__init__.py` 导出节点/WEB_DIRECTORY，注册管理 routes。
2. `web/h3_adapter.js` 配置/发现/模型映射/单独保存 Key；工作流仅存 provider 模式、逻辑 alias、params、nonce，不存 Key。
3. `nodes.py:15-37` 将 BHWC IMAGE 编为 PNG、Comfy 白色 MASK 编为透明编辑区；`:72-74` NaN 让每次排队进入节点；`:76-87` 进入 Engine 并返回实际尺寸 IMAGE/公开状态。
4. `engine.py:50-100` 验证输入 → 稳定请求身份 → 账本；已有 completed/submitting/uncertain/failed/accepted/result_ready 优先按记录缓存或恢复，不按当前模型重新 POST。
5. `engine.py:101-180` 当前配置主备顺序/能力/参数/预算筛选 → SQLite reserve → Protocol 初始化/单次提交 → 记录受理/结果/不明；只有确定安全的拒绝才换家。
6. `protocol.py` multipart 或 JSON 模板/必要上传/正式配置 GET 发现/GET 轮询/单个结果定位和受控下载。`:36-41` 的完整值替换语义是本轮 JSON 校验依据。
7. `engine.py:_recover` + `ledger.py:53-87` 原提交快照、有限轮询、条件状态更新、缓存文件原子替换；已受理恢复不走备用新提交。
8. `scripts/build_release.py` 版本取自 pyproject，排除私密运行数据/环境文件，活跃 providers.json 替换为四商禁用例；manifest 不编造绿色测试。

原版备份：`C:\path\h3-adapter\audit-round3\before`，66 文件的原始 SHA256/长度在 `ORIGINAL-HASHES.json`，修改前已保留。原 0.1.1 ZIP SHA256 为 `0d0e28696652979fc1f26d547a2cf71420ddff1aeae107ddb70bebb84d4d138d`。CRC、54 entries、53 manifest 哈希与旧 DELIVERY SHA 均独立核验；最终新发行包另行验证，不把旧包结果代替新包。

## 2. 裁决总表

| 命题 | 裁决 | 业务判断/行动 |
|---|---|---|
| supports_mask=true 的某些 JSON 模板可能未向编辑 API 传 MASK，却成功 | **CONFIRMED** | 错误配置触发、源码缺少输入消费校验；修请求前校验，不自动猜协议字段。 |
| 所有 JSON Template / multipart 都不能传 MASK | **REJECTED** | 精确嵌套值、真正上传引用、multipart 抓包均含实际 MASK/引用。 |
| 全套异步测试失败证明任务恢复状态机失效或重复扣费 | **REJECTED（针对该失败）** | 失败发生受理前、0 POST/GET，无 task_id；100ms 冷初始化耗尽预算。 |
| 原异步恢复测试有不稳定的受理前提 | **CONFIRMED，测试缺陷** | 用 pending+有限 max_polls 明确建立 accepted，再检验快照恢复；不放宽生产超时。 |
| 本地未发送超时使健康主商被置冷却 | **CONFIRMED，新发现** | 下一正常意图错用备用；仅排除两种安全本地 deadline 的 cooldown。 |
| 同 alias/nonce 改实际模型 ID 后会拿到旧缓存 | **CONFIRMED 现象，作为 Bug 的指控 REJECTED** | 正确付费意图语义；不改 fingerprint/不清账本/不自动 nonce。 |
| 并发迟到结果让 completed 状态/缓存永久倒退 | **REJECTED（已复现路径）** | 条件状态更新保护终态；迟到 pending/GET错误可报告 awaiting，但再次同意图读到缓存，POST1。 |
| JSON 模板丢 IMAGE、只传多图首张、字面 ref 误拒绝 | **CONFIRMED，新发现** | 与 MASK 同一根因，精确消费检查覆盖；不扩多图引用上传。 |
| 有 upload 配置即做未被模板使用的上传 | **CONFIRMED 额外请求** | 改为实际引用驱动；未证明真实多收费，不能把上传次数冒充账单证据。 |
| 保存 Key 时切供应商会把 Key 存到错误商家 | **REJECTED** | POST payload 已捕获正确旧商；不存在本轮证据所称凭证错存。 |
| 上述晚响应会把“已有 Key”标记写到新选择商家 | **CONFIRMED，新发现** | 纯 UI 状态 race；捕获 providerId 并保护当前状态。 |
| 删除文件 Key 后仍有 env Key，界面却显示无 Key | **CONFIRMED，新发现** | 保留 env 优先，只回有效 has_key 布尔供 UI，不回秘密。 |
| 真实供应商协议/MASK效果/费用/RH 都已经可用 | **UNVERIFIED** | 没有真实调用或 RH 实机证据，不能用本地 mock 推出。 |

## 3. 问题一：MASK 请求漏洞

### 原版根因和抓包

原 `engine.py:116-117` 只判断声明 `supports_mask`，`:150-155` 将实际蒙版交 Protocol。原 `protocol.py:163-179` 生成 token，但没有确认 body 实际使用；`_render` 只递归 dict 值/list 并查找**完整相等的字符串**，不会替换键名、拼接片段，也不会再渲染 `{params}` 替换进去的对象。

`audit-round3/protocol/reproduce.py` 默认导入 immutable before 原源码，真实 ConfigStore→Engine→Protocol→HTTPX MockTransport→Pillow/SQLite，20 个案例抓包见 `capture-before.json`。以下均 success：
- body 无 MASK token、仅键名有 token、仅 `prefix {mask_base64}`、MASK token 只在注入 params 内：edit POST1，真正 MASK 没进入编辑请求。
- upload 配置存在但 body 只有 image_ref：image/mask 两次上传、一次 edit；edit 只含第一引用，第二 MASK 引用没有交给编辑模型。
- 无 IMAGE token/仅键/片段：edit POST1，无实际 IMAGE；输入两张不同图、max_images=2 却只用 image_base64：只传首图。
- 合法 inline+字面 `{image_ref}` 键/片段：原 json.dumps 子串检测反而触发 missing_upload_config，与真实渲染规则不一致。

这些模板本身配置有误；但“已连接的输入被无声丢弃并报告成功”不符合适配器 IMAGE/MASK 输入合同，属于源码边界遗漏。不是正确忽略 MASK 的设计，也不是仅提醒管理员就能否认的风险。

### 最小修复及反证

`protocol.py:_template_values/submit` 精确收集可替换的叶子值，任何 upload/edit HTTP 前校验：
- 有输入图必须存在单图/all-image/ref token；多图必须用 images_data_urls；否则 unmapped_images/template_single_image_only。
- 实际 MASK 必须有 mask_data_url/mask_base64/mask_ref，否则 unmapped_mask。
- 真正引用需有 upload，保持引用上传单图边界；只上传模板实际用到的 image_ref/mask_ref。
- 当未接 MASK 时不要求 mask token；仍允许嵌套结构/固定文字/合法 multipart；不猜字段、不把能力当作厂商语义证明。

本地 APIError safe_to_failover：固定错误商家 0 HTTP；auto 错误主商 0 HTTP、合法备用恰好1 edit POST，MASK 字节保留。新18测试 RED 原版17 failure reports（含 subtests，并非17独立Bug），GREEN18通过，见 protocol/red.txt / green.txt。`tests/test_round3_protocol.py` 覆盖正反例、首个上传前拦截、多图、真正引用、字面引用、无用上传和混合 inline/ref。

**拒绝修改**：未接 MASK 的无 MASK 模板不是 Bug；已声明不支持 MASK 的商家被能力筛掉是正确行为；真实引用模式单图限制、单结果抽取是明确范围，不擅自扩协议。字段名配错但 token 仍存在、厂商根本不理 mask 字段、供应商模型能力报错，无法靠通用模板检查证明；须正式文档和实际授权测试。

## 4. 问题二：异步恢复失败究竟在哪里

### 冷/暖初始化证据，不靠加等待解释

本轮原版完整95测试独立连续3次，均在同一 test_accepted_async_task_recovers_only_by_get_on_saved_provider 第一次调用失败：期待 awaiting_result，实际 no_provider。日志 baseline-full-{1,2,3}.log 全保留。

原 `tests/test_engine.py:136` 首轮 timeout=0.1，Engine 总预算包括 Config/图像验证/账本/HTTPX 初始化（原 engine.py:52,77,149-154）。独立真实 loopback 计时 `state/probe-state-loopback.log`：
- 冷初始化110ms，总157ms；POST=GET=0，row ready、task_id=null、预留0。
- 同进程暖初始化15–16ms；POST1、accepted/task-1，后续有限GET/初始化用尽预算时 awaiting_result。

因此该测试没有稳定建立“已受理任务”前提，全套首次冷调用失败不等于恢复状态机丢任务。测试更改仅用已有正常1s预算+服务器pending/max_polls2，明确断言 poll_limit_no_resubmit、accepted/task-1、GET2/POST1；改主商、禁用原商、改原模型/URL后只按存下原快照 GET，成功和下次 cached 共只POST1。没有增加生产 timeout、盲加sleep或改变状态机。

### 新发现的独立真实 Bug：本地过期错误标健康

原 engine.py:166-169 对所有 safe_to_failover 都 cooldown；尚未发送的 request_deadline_exceeded/submit_deadline_exceeded 也进入此分支。state 真 loopback 证据：0POST 后主商 unavailable；下一正常新nonce跳过健康主商，只向p1提交。

修复只在该 safe 分支排除这两个本地 deadline 冷却，原 reject/预留释放不变。已发送响应截止来自 submitted=True，仍 uncertain、保留预留、不换商；accepted直接 _recover，超时也不放回可再次提交状态。新 `test_round3_state.py` 发送前两种phase稳定 RED→GREEN；同nonce/新nonce恢复均主p0。另保留 uncertain/accepted 仅POST1及累计cap阻止新意图的测试。

### 并发、缓存与恢复边界

ledger BEGIN IMMEDIATE + ready 限定保障一个付费claim，mark 的来源状态限定保护 completed。原代码独立 focused 与 late-snapshot 真HTTP重复：迟到 succeeded/failed 不倒退；迟到 pending/GET503 可让其中一个即时响应 awaiting_result，另一个 success，但再次同nonce cached success，POST1/download1。这是不同 caller 的即时快照，不是永久状态丢失。本轮不扩大锁范围，不把所有恢复串行化。

未知已提交且没拿到 task_id 时自动恢复缺少可靠身份，只能 uncertain 阻断并由商家查账；这是保守不重复收费的取舍，不是假装已经恢复。账本存在但结果文件丢失时 blocked，不再付费重做。跨独立runtime/非共享云副本、商家幂等保证、实际上传计费均未验证。上传后阶段不能泛称“0 POST 超时”；上游若对上传单独收费，需核对契约，这个本地冷却修复不提供上传免费保证。

## 5. 问题三：模型、nonce 与缓存

原/现 fingerprint `engine.py:16-21` 输入为 prompt、**逻辑 alias**、provider 模式、params、显式 nonce及图像/MASK字节，不包括服务器当前实际modelID/Key/config revision；engine:83-100优先已有记录及snapshot。`nodes.py:72-74` NaN 明确每次进入Engine，所以该缓存不是 Comfy 没察觉模型配置改变。

原已有合同要求改配置/Key不自动重复既有任务。因此：同 alias/nonce的原请求应恢复原任务、返回原模型/价格快照；若想用新映射**重新付费生成**，明确增加 request_nonce。更改用户输入/prompt/params/alias/provider模式本身也会形成不同意图；“相同 nonce”单独不代表所有输入永远同一请求。

新 state regression 独立证明：原model-p0/0.1完成 → 映射new-real-model/0.7 → 同nonce cached旧model/旧价、POST仍1；新nonce/新alias/新输入分别新ID，POST共4、后续body新model。异步pending换映射也按旧URL/model/task查询，只一个提交。

**REJECTED并拒绝修改**：将实际modelID/config revision放fingerprint、模型切换自动清cache、自动nonce。这些会把配置迁移/原任务恢复变成未显式授权的新付费请求。当前生产 fingerprint/cache/nonce 未改，只补说明和回归。

## 6. 额外确认：密钥界面状态，不是泄密

原 web/h3_adapter.js:205-212，await POST 前 payload是正确旧selected；await 后却写 data.keys[selected]，用户切到b后把a的结果标到b并覆盖其状态。

独立真实 Playwright DOM 运行原 JS（去import并注入app/api，非真实Comfy进程）：保存a假Key→pending选择b→完成→后台a:true/b:false，UI却a无/b有。before/after和重复取证见 config-ui/REPORT.md / 浏览器证据。修复保存时捕获providerId用于POST/更新，晚响应不覆盖其他当前选择状态。

另真实 ConfigStore+原 routes handler（合成Request）：env假Key存在→POST空串仅删除文件Key→GET public仍keys.primary=true。原 UI 从 !!secret 推断 false，与实际 env 优先凭证不符。成功响应只追加有效 has_key **布尔**，前端使用响应，不回秘密；删除/保存真正文件行为、env优先、授权、工作流Key隔离均不变。新前端tests覆盖save/delete、切换/不切换、env仍有效等情况，真实后端route regression验证响应不含Key。

**REJECTED**：“密钥存入新选商家/跨商泄露”。本轮证据只证明错误布尔与即时状态；真实POST始终旧商。没有把UI测试冒充RH秘密隔离验证。

## 7. 全链复核：已实现与边界

| 链路 | 源码/独立证据 | 判断 |
|---|---|---|
| 供应商配置/扩展/CAS | ConfigStore.validate/save/public；配置8进程同revision 1 saved/7 conflict，最终合法；原前端 stale save409回归 | 已实现；不复制节点，不硬编码SubRouter。 |
| 模型选择/能力更新 | JS picker保留auto，改实际ID清mask/maximages/price/defaults/allowedparams；同ID保留确认数据；Engine每次当前cap筛选 | “选择就固定商家”REJECTED；发现不推断cap是正确设计。手改JSON是显式能力声明，不自动猜报价。 |
| 模型发现 | Protocol.discover明确GET配置path+items/id、去重；route discovery:null返回手工ID；前端异步generation与alias/target保护 | 已模拟；不假设所有商家/models。不支持POST发现/分页/专有签名为范围边界。 |
| 编辑协议/结果 | multipart、精确JSON、必要multipart上传、GET轮询、b64/白名单URL单结果；HTTPS verify=True、trust_env=False、retries0、不重定向 | 当前声明范围已测；任意HMAC/gRPC/WS/POST轮询并非只改URL就可覆盖。真实服务待接。 |
| 尺寸与背景 | nodes.image_tensor保留API实际尺寸；round2_images抓包/输出证明MASK传输但输出可改变非蒙区 | 自动缩回/裁剪回贴/逐像素背景锁定不属于通用适配器强制合同，本轮拒绝擅加业务模块。 |
| 主备/防重复/预算 | Engine可用主优先、备按priority；固定/禁auto不备用；safe拒绝可切、不明/受理不切；SQLite预算/跨process claim和currency回归 | 已模拟证明；配置价格是估计，不是商家硬账单；商家安全拒绝码需正式非受理证据。 |
| Key/日志/管理访问 | ConfigStore env优先/private；APIError静态码不原样回body；routes Origin/Host/token/local检查；synthetic Request和真实aiohttp回归 | 已实现；Windows账户ACL/云租户隔离不由chmod保证。配置及runtime仍必须服务端管理员保密。 |
| 节点/发行 | 标准端口/无Keywidget/独立最小图；ZIP版本/CRC/manifest/source bytes/私密排除独立验；唯一Torch项skip | 可以准备免费Comfy实测；未证明完整真实进程或云端可用。 |

### 未掩盖的 Windows 文件替换观测

full-postfix-1 和 -2 各有一次 WinError5，分别不同用例在 ConfigStore.save→atomic_json→os.replace（第二次保存，尚未Engine/HTTP）报拒绝访问；原异步项在两轮已通过。保留原始失败日志，不宣称所有回归轮次全绿。

源码目标read_text上下文会关闭，temp写with退出后replace，持续锁是另一路径.settings.lock；独立100轮save+save+load共200replace/100load探针自己source/target活句柄为0、未再现；后续串行全套通过。**观测 CONFIRMED，源码根因 UNVERIFIED**。没有证据认定杀软、权限平台或句柄泄漏，不加无依据retry/sleep。当前机器间歇性文件占用/权限仍应在真实部署时观察，生产验收不得忽略。

## 8. 开源与官方资料横向取证（不是判断代码对错的替代物）

- [OpenAI Python SDK 实际 images.edit 源码](https://github.com/openai/openai-python/blob/main/src/openai/resources/images.py)：body包含image/mask，extract_files明确提取；佐证“字段接受与真正发出是不同层”，不是本项目所有供应商必须抄其字段。
- [OpenAI 图像编辑官方说明](https://developers.openai.com/api/docs/guides/image-generation)：其 MASK 为编辑指导，不保证精确形状；不能用通用传输正确性承诺逐像素背景保留。只讨论该文档范围，未推断所有模型相同。
- [Comfy 官方节点属性/IS_CHANGED](https://docs.comfy.org/custom-nodes/backend/server_overview)：NaN始终视为变化；当前节点进入Engine与持久付费账本是两层缓存，不应该用自动新nonce替代。
- [HTTPX 官方超时](https://www.python-httpx.org/advanced/timeouts/)：网络子阶段超时不等于绝对总预算。当前总deadline包含本地初始化，100ms冷开销证据来自本轮计时，不从文档猜测。
- [Mask-External-Edit](https://github.com/wuhu290/ComfyUI-Mask-External-Edit)：项目research固定ef38e815...的nodes.py:210-283实际multipart image/mask；:384-407 _paste_back有resize/feather/paste，是特定业务修复链，不能据此判本通用适配器缺合成为Bug。原函数只读，没有复制。
- [HttpRequestNodes](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes)：research固定fdd4827... rest_api_node.py:39-149会在异常/某状态重复send_request，可包含POST；其通用HTTP重试语义不符合未证明远端幂等的付费编辑合同，本项目保守停并不是错。没有移植重试。
- [UniAPI](https://github.com/xiaojuzi2024/ComfyUI-UniAPI)：固定9fad71b...源码INPUT_TYPES有api_key、无MASK端口；直接替换不满足本项目不把Key写共享图和可选MASK合同。固定快照无LICENSE，未复制源码。
- OpenAI SDK本地快照 _base_client.py:885-929包含状态重试/idempotency机制；这是特定服务契约，不给未知中转站通用POST重试授权。本项目不新增供应商硬编码/依赖/Gateway。
- [RH 中国站官方API入口](https://www.runninghub.cn/runninghub-api-doc-cn/)：公开描述提交→taskId→查询结果，本轮重新读取；**推论**：API工作流提交文档不足以证明托管节点上传、任意外连、Key注入与持久卷许可。具体高级接口本轮web抽取失败，旧research HTML仅作已保存来源，未冒充本轮成功获取。

以上网页2026-10-10读取；只用官方/源码和作者一手快照，不从聚合AI文章取事实。细部来源/旧RH证据在现存CANDIDATE-EVIDENCE、GATEWAY-EVIDENCE、RUNNINGHUB文档；旧报告不自动升级为新实测。

## 9. 改动清单、验证与交付

生产业务改动仅：
- h3_adapter/protocol.py：实际IMAGE/MASK消费前置校验、精确引用检测、必要输入才上传。
- h3_adapter/engine.py：安全且未发送的本地deadline不冷却健康商家。
- web/h3_adapter.js：密钥响应绑定保存商家、当前选择状态保护、使用有效Key布尔。
- h3_adapter/routes.py：Key保存成功仅返回has_key布尔；不返回秘密。

测试：新增test_round3_protocol.py（18）、test_round3_state.py（3）、test_round3_frontend.mjs、密钥env后端回归；原test_engine.py改受理前提并增加原任务快照/缓存断言。版本pyproject0.1.2、build仅更新审计证据引用；README/PROTOCOLS/HANDOVER/TESTING、此报告、manifest/DELIVERY/ZIP同步。没有改nodes/ledger/config架构、协议字段模板、工作流、依赖、许可证。

最终源码独立串行两轮均 **117 tests：116 passed、1 skipped、0 failure/error**（final-source-unittest-1.log / -2.log）；唯一跳过为真实Torch Tensor往返，不能算通过。前端基础契约通过、review 15/15、新密钥状态6场景通过；JS语法和27个Python文件AST校验通过。原版3次失败及修复中2次WinError5同样保留，未用最终绿日志抹掉历史异常。最终ZIP解压回归统计由独立日志及DELIVERY记录，不以源码通过代替包验证。

本轮取证和验证的全部原始结果保留在 `C:\path\h3-adapter\audit-round3`：
- before/ORIGINAL-HASHES.json；baseline-full-{1,2,3}.log（原版真实失败）。
- protocol/{capture-before.json,reproduce.py,red.txt,green.txt,REPORT.md}。
- state/{probe-state-loopback.log,round3-state-red-focused.log,round3-state-green.log,focused-green-*.log,late-snapshot.log,config-handles.log,REPORT.md}。
- config-ui/REPORT.md 与测试/真实DOM记录；cross-review.md（独立只读交叉复核）。
- final-source-unittest*.log / final-frontend*.log / package-unittest.log / package-frontend*.log / package-verification.json（以实际日志结果为准，最终DELIVERY记录）。
- CHANGES.json / CHANGES.patch 保存修改前后哈希/新增文件/文本差异；源码报告中的原版行号始终指before，不混用改后行号。

复跑（PowerShell，已有依赖；只用loopback/MockTransport/假Key）：
```powershell
$r='C:\path\h3-adapter'
$env:TEMP="$r\work\tmp"; $env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONIOENCODING='utf-8'
Set-Location "$r\ComfyUI-H3-Adapter"
& "$r\work\venv\Scripts\python.exe" -m unittest discover -s tests -v
node tests/test_frontend.mjs
node tests/test_frontend_review.mjs
node tests/test_round3_frontend.mjs
```

正式ZIP在 releases/ComfyUI-H3-Adapter-0.1.2.zip；源码自有MIT，HTTPX BSD-3-Clause/Pillow MIT-CMU原LICENSE字节与已安装依赖匹配，没有新增第三方源码。包构建器仍明示not_executed_by_package_builder，不伪造固定通过计数。最终实际验证统计/ZIP SHA见项目根DELIVERY.json及package-verification.json，分开源码和解压包结果。

## 10. 能否实测与距离生产标准

**可进入测试：可以，限受控普通 ComfyUI 免费mock验收。** 先用用户已有Comfy Python跑真实Tensor跳过项，再安装0.1.2、检查object_info/扩展加载/管理route，导入本项目独立最小图，验证成功IMAGE尺寸、status、MASK、主备、同nonce恢复、新nonce显式新任务、失败空batch对SaveImage的处理。测试过程不改既有H3生产图，也不发收费请求。

**生产：不达标。** 仍缺：
1. 真实PyTorch与完整Comfy进程成功/失败图、当前frontend/browser版本验收；本机缺Torch，skip不是通过。
2. 目标各供应商正式编辑/上传/MASK/多图/发现/异步状态/拒绝码/计费契约，以及另行授权的最小真实调用；不能把尚未接通称为程序Bug，更不能说已经可用。
3. 真正去人/墙门窗补全效果和背景约束验收；若需要硬保留非蒙区由独立背景修复模块定义合成，不在本轮凭外审意见加功能。
4. RH本节点收录/私有上传批准、Python依赖与WEB_DIRECTORY/管理route、API/上传/轮询/CDN每个HTTPS域名和鉴权头出站许可、云端安全秘密注入/租户隔离、共享持久runtime/副本一致性以及RH实际执行证据。
5. 商家账户硬预算、未知提交查账/恢复操作规范、缓存/账本保护和磁盘/文件占用观测。local估计cap不能控制真实报价，也不等于商家跨副本全局幂等。

普通Comfy扩展接口依据、本地mock通过、RH目录收录、RH允许上传、RH允许出站、RH实机出图是分别的证据。本轮未把它们混为同一“兼容”。完成本轮后停止，不擅自测试真实商家、安装进其他项目或继续扩功能。
