# 第二轮独立源码审计 — H3 通用 API 适配器 0.1.1

日期：2026-10-10。审计和修改范围仅为 `C:\path\h3-adapter`。收费 API 调用 0；真实密钥使用 0；未推送远程；未修改 H3 主链、Z-Image 原始 JSON、Background Core。

## 0. 判定方法与证据位置

没有收到上一轮“外部审计”的完整原文，因此本报告逐项独立核验本次用户列出的风险，不冒充对未提供报告逐句复核。CONFIRMED 必须有真实调用链和复现；REJECTED 表示所述问题/修复要求不成立；UNVERIFIED 表示缺少验证条件，并不等于程序 Bug。

已完整读取 用户指定的 Skill 根目录 下的全局看代码逻辑、调Bug、省代码总规则、联网资料过滤器及关联审查要求；读取了本轮相关调试、回归、验证技能。检查对象包括全部核心 Python 模块、节点输入/输出、管理路由、前端扩展、配置和示例、原有及新增测试、构建器、原发行包；另外三个隔离子审计分别复核 UI、执行/账本、配置/发行与上游证据。先使用原版本复现，再写 RED 回归，最后在现有架构中最小修补；没有换 Gateway、复制供应商节点或增加背景业务链。

修改前备份：`audit-round2/before/`；原始文件 SHA256 清单：`audit-round2/before/ORIGINAL-HASHES.json`。原 0.1.0 ZIP 的 SHA256：
`5d8dddc9657014149257a9b67cb3c0b32e9623086efdeda7f02bc6cc849f0681`。
备份保留了源码、测试、配置模板、说明和旧 ZIP，没有复制运行时私密图像和真实密钥文件。修改清单、原/新哈希及完整差异见 `audit-round2/CHANGES.json`、`audit-round2/CHANGES.patch`；最终 ZIP 信息见根目录 `DELIVERY.json`。

以下行号明确标为“原版”的均对应 before 快照；现版优先以函数名和回归测试名定位，避免日后加注释使行号失效。包内路径均相对于 `ComfyUI-H3-Adapter`。

## 1. 结论摘要

| 风险 | 独立判定 | 处理 |
|---|---|---|
| 选模型会把 auto 隐式改为固定家，备用失效 | CONFIRMED | 修复，保留当前调度模式 |
| 改模型 ID 沿用旧 mask/报价/defaults 等 | CONFIRMED | 修复，改 ID 后回到保守未知状态 |
| 别名切换、异步切供应商导致映射写错 | CONFIRMED | 修复，刷新别名、保存目标在 await 前捕获 |
| 多窗口旧配置覆盖最新报价/能力/主备 | CONFIRMED | 修复，UI revision + 锁内 CAS，冲突 409 |
| 数项不合法配置成功保存但执行异常/语义错误 | CONFIRMED | 最小字段校验，拒绝保存且原配置不变 |
| 旧零价任务破坏后续有限预算预留 | CONFIRMED | 修复变量遮蔽 |
| 旧任务费用被标成当前新币种 | CONFIRMED | 修复，使用账本原币种 |
| GET 慢速响应及初始化消耗绕过总等待预算 | CONFIRMED | 增 GET deadline 检查、POST 前重新检查剩余时间 |
| 并发恢复把 completed 回退，丢失可读缓存状态 | CONFIRMED | 限制状态迁移，读取已完成状态 |
| 确定未发送的非法鉴权头被锁为 uncertain | CONFIRMED | 在发网络前明确拒绝，允许安全备用 |
| 构建器版本/测试“证明”写死，可能生成假元数据 | CONFIRMED | 从版本文件取值；构建器不声称自己执行测试 |
| 构建器会收进 .env 凭据文件 | CONFIRMED（构建输入风险） | 排除常见 .env 和 SQLite 辅助文件；旧包无真实泄漏证据 |
| 输出尺寸不同就应自动缩放/回贴、MASK 必须保证像素不变 | REJECTED（作为通用适配器 Bug） | 不添加未来背景模块功能 |
| 已受理但断连会自动向备用再次收费 | REJECTED（本适配器现有调用链） | 原版真实 TCP 复现为 1 次 POST、uncertain、无备用 |
| 所有未真实接通供应商都应判程序 Bug；普通 Comfy 可用=RH 已可部署 | REJECTED | 区分协议边界与未验证环境 |
| 真人移除质量、真实供应商、完整 Comfy/PyTorch、RH 实机 | UNVERIFIED | 明确列出验收条件，不伪造通过 |

不是“原来的 69 个测试通过所以没有风险”：原前端测试甚至明确断言选模型后 provider 变成 primary，验证的是错误业务约定。本轮修订该断言并补独立回归。也不是“外部审计说缺能力就增加能力”。

## 2. 模型选择、能力、报价与费用限制

### CONFIRMED：隐式固定供应商

原 `web/h3_adapter.js:274–277` 在保存选择后调用 `setWidget(node, "provider", provider.value)`。真实链为：
模型 picker 保存 → node.provider 从 auto 变 primary → `nodes.py:H3ImageEdit.edit` 原样传 provider → `engine.py:Engine.edit` 原版 100–105，provider 非 auto 时 order=[provider] → auto_failover 即使为 true 也没有备用。

这不是 Engine 固定模式本身的 Bug：手动明确固定一家本来就必须不切换。问题是“选择实际模型/维护映射”被偷偷等同于“固定调度模式”，违背自动模式 + 主备业务合同。现版 picker 不改变 node.provider，manager 的明确固定供应商操作仍保留。自动模式映射选中供应商的逻辑别名，不代表切换实际调用的主家。

### CONFIRMED：旧模型元数据继承和错误映射

原版 picker 将旧模型对象 spread 后仅替换 id，因而模型 A 的 supports_mask=true、max_images=8、mask_encoding、price_upper_bound=0.1、defaults 和 allowed_params 可以带给 B。Engine 会据此编码 mask、放行参数、估算费用；这不是纯显示问题。

现版：只有真实 ID 未变时保留已确认元数据；ID 变化/新别名时设置 task=image_edit、supports_mask=false、max_images=1、price_upper_bound=null、defaults={}、allowed_params=[]，移除旧 mask_encoding。显示能力/报价待重新确认的警告，异步发现结果不能覆盖该警告。未从模型列表臆造“支持 mask/报价”。有限预算下未知价格被 Engine 排除，是正确的保守结果；用户需依据正式 API 在配置管理器确认新模型能力和保守报价。

另两项真实 UI 缺陷：原别名输入无 onchange，旧 ID 会写入另一个已存在别名；保存 latest-config 的 await 期间换供应商，后续取当前控件值会写错家。现版分别刷新 ID、在 await 前捕获别名/ID/供应商。

### CONFIRMED：并发配置覆盖

原 manager 整份提交打开时快照；picker 即使先 GET 最新配置也有 GET→POST 窗口，两者均能将新报价/能力覆盖为旧值。现 `config.py:ConfigStore.revision/save/public` 生成规范化内容 SHA；save 在 settings_lock 内比较 revision 和原子替换；`routes.py:save_config` 冲突返回 409；manager/picker 都发送 expected_revision，并在成功后更新本地 revision/缓存。冲突后应保留编辑内容、重开/刷新并合并，不能盲目再次覆盖。

兼容边界：旧程序直接调用 save/POST 不带 expected_revision 仍可最后写入覆盖；本次 UI 使用 CAS，不能声称未升级的第三方写入方也自动受保护。

证据：
- `audit-round2/ui/ui-repro.log`、三组 RED、`ui-regression-green.log`。
- `tests/test_frontend_review.mjs` 15 项：auto/fixed 保留、改 ID 清旧属性、同 ID 保留、未知报价、别名切换、请求中切家、CAS 冲突/缓存/警告。
- `tests/test_round2_concurrency.py` 两个真实 aiohttp 路由测试，旧 revision 返回 409、不覆盖新报价；成功保存 revision 可继续衔接。
- `audit-round2/cas-red.txt`、`cas-green.txt`。

### REJECTED：发现列表应该自动决定能力/价格；换模型必须自动提高费用上限

发现 ID 不证明编辑能力、mask 语义或账单。用户的 max_cost/max_total_cost 是独立限制，换模型不应擅自抬高或替换限制。本次修复清理的是不再可信的模型报价和参数，不是放宽预算。仍须手动维护保守价格；这是配置驱动合同，不是假装拥有商家计价接口。

## 3. 尺寸、MASK 和未遮挡背景

真实链：`nodes.py:png_inputs` 将 IMAGE 转 PNG，Comfy 白色编辑 mask 转透明 alpha；`engine.py:provider_mask` 依据已声明的 grayscale_white_edit 转换；Protocol 上传；Engine 只验证有效图像/大小上限并缓存返回字节；`nodes.py:image_tensor` EXIF 校正、转 RGB/BHWC，使用上游实际宽高。

外部输入 16×8、返回 4×6：输出就是 4×6，没有强制 resize、裁剪或贴回。纯 Engine 回归验证返回字节完全相同；节点 tensor 代码无 resize。现协议一次取一个结果，所谓“多结果不同尺寸 torch.cat 必然出错”目前没有可达调用路径，不据此重构。

输入 MASK 是供应商编辑指导，不是本地硬性像素门控。已声明 mask 能力时真实发送 mask，不支持时能力筛选拒绝，不静默丢弃；但供应商仍可能改动黑色未遮挡区。测试将输入全红、mask 一部分白，模拟 API 全蓝输出；现版如实输出全蓝，不做本地合成。

**REJECTED**：把未自动保尺寸/保背景像素认定为通用接口转换缺陷。本项目合同是 IMAGE→外部编辑→IMAGE，以及真实声明 mask 支持，不是保证修复结构、视觉一致性或逐像素不变。背景业务模块若今后明确需要，应另行负责输出对齐、尺寸策略、ROI/裁剪回贴、mask 混合、接缝/色彩和建筑结构验收；盲目把不同尺寸结果缩放再贴回并不保证语义对齐。本轮拒绝添加这些功能。

证据：`tests/test_round2_images.py` 两项，无需 Torch；原版和现版均通过，`audit-round2/image-boundaries.txt`。官方 IMAGE/MASK 约定：[Comfy 文档](https://docs.comfy.org/custom-nodes/backend/images_and_masks)。模型可能将 mask 作为指导而非逐像素承诺，见[正式图像指南](https://developers.openai.com/api/docs/guides/image-generation)。候选 [Mask External Edit 源码](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/main/nodes.py) 的 _paste_back 是一个有明确局部处理目标的业务节点实现，不能自动成为所有通用适配器的必备合同。

**UNVERIFIED**：实际供应商输出比例/质量、模型 mask 效果、真实 Torch 到 Comfy 的运行。空 IMAGE batch 是失败而非原图伪成功；官方 SaveImage 会取 images[0]，连接空 batch 可令下游报错。该失败图的 UI/业务处理需完整 Comfy 验收，不能把状态报告存在等同于整张图还能成功完成；本轮未擅自返回原图或新增分支节点。

## 4. 主备切换、提交不明和异步恢复

### REJECTED：已受理断连会自动再次付费

独立原版真实 loopback TCP：primary 收到 POST 后断开；第一次 uncertain，第二次同输入/nonce previous_submission_unknown_no_resubmit；primary 总 1 POST，备用 0。见 `audit-round2/scheduler/evidence.json` 的 accepted_disconnect 与 `scheduler_repro.py`（默认针对 before）。

链条：`ledger.py:Journal.begin/reserve` 在发 POST 前事务占位；`protocol.py:_request` retries=0；读/写异常、5xx 等为 uncertain；`engine.py:Engine.edit` 不 safe_to_failover 时持久 uncertain 并退出。异步 task_id 已知只查询同家任务；远端 failed 不自动付费重做。配置变化、换 Key、同 nonce 重新排队不能抹掉已受理意图，这是有意防重，不是“用了旧映射”的 Bug。

只有已知未发送的连接失败/连接或池超时、已明确非受理的允许 4xx/本地预检错误才切换。safe_reject_statuses 的非受理含义仍需商家文档；429 不能不经验证随意加。未知 upload 结果也保持保守，不将可能计费的上传一概当免费。SQLite 的保护范围是共享同一持久 runtime 的实例，不是跨商、跨云副本的全局幂等服务。

### CONFIRMED：可靠性缺陷，已最小修复

1. **预算变量遮蔽**：原 `ledger.py:reserve:63` 循环把字符串 model 参数换成旧记录模型 dict；有限总预算下出现零价历史，下一次 reserve SQLite 绑定失败。改为 previous_model。回归两次不同 nonce，第一笔 0、第二笔 0.1，均成功。
2. **异步并发状态回退**：同一个 accepted 任务两个恢复线程，较晚 succeeded/failed 可覆盖已经 completed 的状态，下一次结果无法读取。现 Journal.mark 只允许合法源状态迁移；Engine 在终态后重读 row，优先读 completed 缓存。真实 HTTP 两种晚响应回归保留成功缓存，没有新增 POST。
3. **GET 总预算**：原 poll/download/discovery 仅 HTTPX inactivity timeout，持续小块返回可超过等待预算。现均传单次 monotonic deadline、读流检查剩余；POST 前在 Protocol 初始化和 mask 编码后重新检查，避免这些工作消耗预算后还发提交。慢响应和慢初始化回归均有 RED/GREEN。HTTPX 的网络等待 timeout 不等同绝对墙钟截止：[官方说明](https://www.python-httpx.org/advanced/timeouts/)。这是协作式预算，阻塞网络操作可能有调度/读超时粒度偏差，不宣称硬实时或已取消远端工作。
4. **非法 auth 头预检**：非 ASCII、CR/LF、NUL、头值边缘 SP/HTAB 本地一定无法发送时，原来统一转 transport_uncertain，0 POST 却永久占用付费意图。现 _headers 先拒 invalid_auth_header，释放已知未提交预留、可换家。仅拒确认的编码/头值条件，不凭猜测禁合法字符。
5. **历史币种**：完成/不明/accepted/failed 的报告原来沿用当前配置 currency，把旧 USD 估计标为 CNY。现从账本 row 的 currency 取历史币种，价格仍来自原 snapshot。

证据：`tests/test_round2_scheduler.py`；`audit-round2/scheduler/SCHEDULER-AUDIT.md`、`production.patch`、`original-before-all-red.log`、分项 RED/GREEN；头值追加真实 loopback 交叉复现见 `audit-round2/config/cross-review-invalid-header-current.json` 和 scheduler 新回归日志。

### 仍需操作规程，而不是擅自自动恢复付费

提交窗口 crash / 无 task_id 的 uncertain：不能判断零提交还是已收费，只能保守停住。必须商家查询账单/任务、提供按客户端 ID 查询或正式幂等契约，才能进一步自动处理。旧版已经锁住的 uncertain 不自动清空；修复头值后原未知任务仍需人工核对，新 nonce 代表用户明确允许一笔新付费。删除账本、换 runtime、缓存丢失会失去/阻塞恢复；signed URL 过期也可能无法下载，需要商家正式刷新流程。不要为“更方便切换”取消防重。

## 5. 供应商协议兼容性

**已实现且模拟验证**：配置式 Base URL + 路径拼接、服务端 Key/auth header/prefix、逻辑别名到不同真实 ID；multipart 编辑或 JSON 精确 token 模板；可选一次上传引用；单张 b64_json/URL 返回；异步 GET 查询；显式 discovery API 路径/嵌套字段，缺接口用手填。四个占位供应商及更多列表条目无需复制节点，无 SubRouter 业务硬编码。

**不是任意协议万能翻译器**：当前不支持 HMAC/OAuth 复杂签名、WebSocket/gRPC、POST 查询、原始图片响应体/任意 data-URL 输出、多结果聚合、分页/顶层数组发现等；JSON 参数如何进入模板必须符合现有精确 token 合同。API 返回域名还受结果 download_hosts 策略限制。不同商家能力/参数不能仅改 URL 就自动等价。未知/这些边界协议可用受控网关归一化，或在取得正式文档后批准一个具体新协议；本轮不为未来猜接口。

**REJECTED**：把某个未公开协议未接通直接认定为代码缺陷；把正式 discovery 缺失当不能调用。当前是明示协议族内配置替换，而非保证任意中转只填三字符串便支持所有功能。

**UNVERIFIED**：SubRouter 真实编辑模型、multipart/JSON、mask、价格、正式发现/异步/结果域名；其他真实供应商同样未接通。本轮不调用收费接口，不读取真实 Key。真实验收需要正式请求/响应和能力文档，不需要把 Key 发到聊天。已复核的 RunningHub 节点使用 POST 查询，说明协议差异真实存在，不说明本适配器“假装支持 POST”。

## 6. 配置、Key、日志、并发和发行

### CONFIRMED：保存入口的局部校验缺陷

`config.py:validate` 原来允许下列值保存成功，之后执行失败/语义改变：
- key_env 的 null/false/0/列表/对象，使私密 Key 查找或 public 管理 GET 崩溃；
- allowed_params 元素为对象/列表，Engine set() 异常；
- async success/failure 为字符串，poll 用字符串 membership 导致部分状态词被误认成功；同时拒重叠终态和 bool poll 数值；
- max_response_bytes 为浮点，保存通过但 Protocol 拒绝；
- 全局 timeout_seconds/cooldown_seconds=null，前者预算计算失败，后者首次明确拒绝后阻断备用；
- 全局 auto_failover="false" 是 truthy，实际仍切换。

现版拒绝这些值，错误发生在 save 边界而非付费执行中；max_total_cost=null 仍是合法无累计上限。不把这次局部修复包装成覆盖所有外部 JSON 的完整 schema 重构。

证据：`tests/test_round2_config.py` 11 个方法/多子例，测试实际 ConfigStore.save 并验证原配置没有被覆盖；`audit-round2/config/tdd-red-save-boundary.log`、`tdd-green-save-boundary.log`、`tdd-red-global.log`、`tdd-green-global.log`。priority 的异常值原版已拒绝，相关指控 REJECTED，增加覆盖而未重复改逻辑。

### REJECTED：当前工作流/报告已泄露真实 Key、原 ZIP 与原源码不一致

Key 没有 node INPUT_TYPES，ConfigStore.public 只给 keys 布尔值；环境变量优先，私密文件另存；报告用静态错误代码，不附商家正文、异常文本、signed URL。现 synthetic secret 回归、12 个独立 Windows 进程并发私密保存均通过，无已证实跨 provider 读取/丢失。管理跨源/Forwarded/token 检查存在，原路由测试已证明拒绝；没有因为“云端可能代理”擅自关闭限制。

原 ZIP CRC、46 个 manifest 文件哈希、源码字节比对一致，包含一个 manifest 共 47 个条目；没有真实密钥泄露证据。**但这不等于生产多租户隔离认证**：本服务是受信管理员维护配置，不是给每个普通工作流用户分配独立商家 Key 的密钥托管服务。runtime 有私密图像、商家临时 URL，Windows chmod 不是 ACL；云端账户/持久卷必须另验。

### CONFIRMED：构建器的未来泄漏/假证明风险

原 builder 将版本固定 0.1.0，并固定“70 tests/69 passed”而不执行测试，未来版本会产出错误版本和伪测试证明。现从 pyproject.toml 读取版本，manifest 明确 not_executed_by_package_builder，独立证据指向此报告。假目录加入 .env 等后原 builder 收入 ZIP（复现只使用假 Key）；现排除 .env/.env.*/ *.env 和 SQLite 辅助文件。证据 `tests/test_round2_release.py` 三项及 release-*.txt、config/builder-dotenv-repro.json。

仍采用最小排除式打包，**不是任意秘密文件扫描器**；随意命名的 credentials.txt 或把私密运行目录改到包内其他名称仍可能打包。保持秘密/runtime 在约定 private 路径或包外，发布者必须复核文件清单。不能将“旧包没漏”说成“将来任何输入都安全”。

## 7. 独立开源对照与许可证

没有因为候选 README 好看就搬入运行时。保留现有轻量 Adapter + HTTPX + SQLite 架构，自有源码 MIT；HTTPX BSD-3-Clause；Pillow MIT-CMU，原许可证文件保留。没有复制 UniAPI 无 LICENSE 快照的实现，没有新增复杂 Gateway 或云服务。

| 实际源码/固定证据 | 对本轮业务判断的影响 |
|---|---|
| Mask External Edit，ef38e815c004c3ad68b5c486c1ffe518183aad00，MIT；nodes.py _paste_back/provider selection | 有意的局部背景回贴和固定供应商不是通用自动调度合同，拒绝无证据移植 |
| HttpRequestNodes，fdd4827090dcc02d900c0e60338fcc06cb7b0bac，MIT；rest_api_node.py HTTP/retry loop | 通用 HTTP 节点没有本项目付费意图账本，不能为省代码恢复无限/宽泛 POST 重试 |
| UniAPI，9fad71b7f08a6fd71216ef0562b048e5526d7179，README 宣称 MIT 但取证快照无 LICENSE | 不作为可直接复制来源；协议和轮询仍需真实源码，不能把文案当合同 |
| OpenAI Python 官方 _should_retry | 默认宽泛重试含 5xx 等，不可直接作为跨商付费 failover 依据 |
| LiteLLM bbc8d663234d7b464c65dfb93547de3d0b680560、Portkey 669825cbe89ee51569918b8f78a9db486fd69dd4，本轮复核许可/源码 | Gateway fallback 可参考，但不自动等于本地单笔任务跨商 exactly-once |
| HTTPX timeout 文档和源码 | read timeout 是网络等待而非完整操作绝对 deadline，支持本轮慢流缺陷判断 |
| HM-RunningHub/ComfyUI_RH_OpenAPI 7f1160f5a66e5e96659577bcb2df18668cf6ace4，api_key.py/task.py | RH 自有系统 Key 机制不等于任意商家 Key 托管；POST 查询暴露真实协议边界 |

固定快照和许可原文在项目 research/ 与包 docs/*EVIDENCE.md；本轮再次抓取 SHA/hash/内容在 `audit-round2/config/pinned-upstream-verification.json`、`current-upstream-commits.json`、`current-primary-fetches.json`。联网过滤器尝试搜索服务失败后采用官方站点/官方仓库匿名 HTTPS，不使用论坛转述作为定论。
可查原始实现：[HTTP 节点](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes/blob/main/rest_api_node.py)、[OpenAI 重试源码](https://github.com/openai/openai-python/blob/main/src/openai/_base_client.py)、[RH 开源节点](https://github.com/HM-RunningHub/ComfyUI_RH_OpenAPI)。以上并不构成本适配器已经真实部署的证明。

## 8. RunningHub：逐项证据，不能合并

| 命题 | 本轮状态 |
|---|---|
| 后端/前端接口采用标准 Comfy 自定义节点方式 | 源码成立；完整进程仍 UNVERIFIED |
| 大陆 RH 节点库已收录本适配器 | UNVERIFIED，无收录记录 |
| RH 允许当前账户上传/安装此 ZIP | UNVERIFIED，无平台批准/安装结果 |
| RH 服务端能访问自定义 API/CDN 和鉴权头 | UNVERIFIED，无云端网络实测 |
| RH 能安全保存任意供应商 Key、有租户隔离和持久账本 | UNVERIFIED |
| RH 实机 IMAGE→编辑→IMAGE 已成功 | UNVERIFIED，未执行 |

正式 [RH 创建任务文档](https://www.runninghub.cn/runninghub-api-doc-cn/api-425749013) 允许调用者传工作流 JSON，不提供安装未收录 Python 代码的证明；[RH 工作流示例](https://www.runninghub.cn/runninghub-api-doc-cn/doc-8287342) 的客户端调用条件也不是 RH 服务端外连许可。官方页面快照和 SHA256 在 current-primary-fetches.json。公开 RH 节点的 shared_api_key 是系统自身账户机制，不能推论任意商家秘密都能注入，不能复制打印密钥片段的方式。

最小待验收：平台确认节点安装/前端加载 → 实机 object_info/导入 → Python/依赖/文件权限 → API 和结果域名 TLS/外连/鉴权 → 秘密注入及持久共享 runtime → 免费 mock/模型发现（先确认免费）→ 用户另行授权一笔真实编辑、恢复/缓存、尺寸和 mask 质量。没有许可时保持自控 Comfy 或获批桥接网关方案，不绕过平台政策。

## 9. 本轮验证、发行与下一位 Agent

源目录最终独立执行：
- Python unittest：95 项，94 通过，1 skipped，0 failures/errors。skip 是没有 PyTorch 的真实 tensor round-trip，不计为通过。
- 原 frontend 合同测试通过；新增前端 15/15 通过。
- Python compileall、JS node --check 通过。
日志：`audit-round2/final-unittest.txt`、`final-frontend.txt`、`final-frontend-review.txt`、`final-syntax.txt`。
首次最终回归暴露原 test_engine 以 20ms 总预算同时测初始化与已发送读超时的竞态：新预提交 deadline 正确阻止发送时返回 no_provider。仅将此测试分离为 1s 总预算、主家 20ms 网络预算、服务端 200ms 延迟，继续断言主家恰好一次 POST/无备用；没有放宽生产 deadline。首次失败和修正后结果保留在 final-first-run-failure.txt、read-timeout-fixture-green.txt。

这是原版反例 + 当前回归证据，不能扩展为真实商家或 RH 成功。

0.1.1 安装包：
`releases/ComfyUI-H3-Adapter-0.1.1.zip`；SHA256 见 `releases/SHA256SUMS.txt` 与 DELIVERY.json。
发布后独立解压，CRC/manifest/源码逐文件比较、无秘密/运行时/bytecode、模板禁用全部四家；再用解压包运行 Python 与前端测试。最终结果见 `audit-round2/package-verification.json`、`package-unittest.txt`、`package-frontend*.txt`。发行包测试目录保留在 audit-round2/package-check，不修改安装包内业务配置。旧 ZIP 只留在 before，避免误装。
历史 docs/VALIDATION/REVIEW/TESTING/HANDOVER 的 0.1.0 结果已标记历史，不能覆盖此轮结果；builder 自身不宣称测试已执行。

### 可测试标准与生产标准分开

**可测试：达到受控本地免费/mock 核心验收标准，可交给有真实 Comfy/PyTorch 的测试环境安装验收。** 不能说完整 Comfy UI 已跑通；本轮保留一个真实 tensor skip。主备、重复请求、错误、预算、并发恢复、配置冲突、UI 模型映射和包一致性有本地证据。

**生产：未达到。** 阻断条件是完整 Comfy 的成功/失败图验收、至少一个正式供应商真实图像编辑/能力/价格和结果域名验证、付费对账/uncertain 操作规程、目标 RH 安装/外连/秘密/持久卷实机验证。多个供应商只有符合现有协议且能力同类时可配置替换；不宣称任意未知协议零代码接入。

继续工作的明确边界：
1. 不修改 H3/背景链；先测试独立例图。
2. 用正式 API 契约配置，不以目录页推测 mask/价格/路径；新 ID 后重新确认元数据。
3. 旧 uncertain 不清库不擅自新 nonce；先对账。未知价格在有限预算下不调用。
4. shared runtime 只保证该共享账本内防重；云端多副本/重启必须验证存储。
5. 保持私密目录不进入 ZIP；发布跑测试并核对 manifest，不相信构建器代测。
6. 背景一致性若后续要求，单独定义业务模块和验收，不把接口适配器变成隐式图像修复器。

完成本次审计后停止，等待下一步指令。

