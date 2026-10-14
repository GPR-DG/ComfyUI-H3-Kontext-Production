# H3 通用 API 适配器：第五轮独立审计与 0.1.4 交付

审计日期：2026-10-11，Asia/Shanghai。唯一项目目录为桌面 h3适配器；本报告路径以插件目录为根，原始日志位于其上级 audit-round5。结论依据现有源码、真实 loopback HTTP 请求、锁/账本和发行实验；历史报告只作为线索。零收费调用、零真实 Key、零远程推送。未修改 H3 主流程、Z-Image、Background Core、人物模块或其他项目。

## 当前结论与边界

三个主要疑问中：发行黑名单绕过风险 CONFIRMED；JSON 固定字段的合法性 REJECTED（拒绝强制占位符），静默未映射的报告问题 CONFIRMED；Key 同身份同 revision 的最后写入者生效 REJECTED（不是丢失更新）。进一步确认非法 multipart 字段在尚未 POST 时被误分类为付费未知，已最小修复。旧正式 0.1.3 ZIP 未发现实际泄密证据，不能把可复现的构建风险写成已经发生的密钥泄露。

当前可准备普通 ComfyUI 免费受控测试，不能称完整实机已验或生产稳定版。Windows os.replace 的 WinError 5 在本轮多次测试复现，既发生于秘密文件，也发生于普通配置；根因、目标存储稳定性 UNVERIFIED。没有证据把异常归因于杀毒、索引、只读属性或特定进程，也没有加 sleep/retry 掩盖异常。

## 已独立复核的源码链路

| 入口 / 行为 | 源码、函数与调用关系 |
|---|---|
| 节点与图像端口 | `__init__.py` → `nodes.py:H3ImageEdit` / `png_inputs` / `image_tensor` → `Engine.edit`；注册 H3ImageEdit，WEB_DIRECTORY=./web，返回 IMAGE、provider_model、status_report |
| 管理与模型发现 | `web/h3_adapter.js` → `routes.py:register_routes`（config/key/models）→ `ConfigStore` / `Protocol.discover`；发现依据可选配置，不假定统一 /models；允许手填模型 |
| 配置、Key、身份 | `config.py:validate/save/save_key/credential`；settings_lock 保护配置与秘密 read-modify-write；revision 是非秘密配置哈希，环境变量优先；credential 原子捕获身份和 Key，恢复用身份/秘密指纹 |
| 调度与费用 | `engine.py:edit` → `Journal.begin/reserve/mark/reject/cooldown` → `Protocol.submit`；主家优先、备家 priority 稳定排序、能力/参数/价格筛选，不限于三备；账本 SQLite 事务保护去重和预留 |
| 请求与输入 | `protocol.py:_render/_template_values/submit/_upload/_request`；完整值替换，IMAGE/MASK 先验映射；multipart 字段先验验证；上传、编辑、轮询、下载共用剩余预算 |
| 受理及恢复 | `engine.py:_recover` → `Protocol.poll/result` → `Journal.mark`；accepted/result_ready 仅恢复原任务，uncertain/submitting 禁新 POST；完成终态不能被晚到并发轮询覆盖 |
| 发行 | `scripts/build_release.py:RELEASE_FILES/build` → 禁用 example 前置检查 → 写 manifest/ZIP → 每项 hash 与 ZIP CRC 验证；active config 由 example 替换 |

生产模块、入口、前端、依赖和构建器已整体追踪；新增测试及关键历史调度、并发、凭据、恢复、发行测试已逐项复核。未声称全部历史报告及所有测试正文逐字阅读；结论以实际调用链、关键断言及本轮完整执行为依据。

## 三组疑问的独立裁决

### JSON 模板

`Protocol._render` 只替换完整字符串值，嵌套字典值/数组同样支持；键名和 `literal {prompt}` 不插值，注入 params 不二次递归。固定模型/提示词是既有合法合同，强制 `{model}` / `{prompt}` 会破坏专有 API，REJECTED。实际复现捕获 model=fixed-model-B、prompt=fixed prompt，而配置映射为 edit-model；因此“界面模型一定等于 HTTP model”不成立，缺少说明的风险 CONFIRMED。

修复仅在 `Engine.edit` 生成 warnings：json_template_unmapped_model、json_template_unmapped_prompt、有有效参数但未用 `{params}` 时的 json_template_unmapped_parameters。report.model 仍为配置映射，不能据它断言供应商实际模型。警告不更改 body、不阻止合法常量模板，缓存/异步恢复保留，切换备用时重新计算。警告不等同于验证供应商实际采用了任何字段。嵌套 token 对模型、提示词、参数的变化捕获已通过；IMAGE/MASK 属于必须显式映射的实际输入，与固定文字合同不同，不放松现有 IMAGE/MASK 拒绝规则。

### 发行与 Git

原构建器递归收集后按名称黑名单排除。模拟 11 个文件：config/secrets.private.json.bak、config/providers.backup.json、config/key-store.json、debug.log、tokens.txt、session.db、web/key-copy.js、h3_adapter/key_copy.py、docs/private-notes.md、scripts/debug_key.py、tests/test_secrets_copy.py，均能进入原 ZIP；部分断言在 ZIP 已写出后才失败。release-before.txt、reproduction-before.txt 为 RED 证据。构建缺陷 CONFIRMED。

0.1.4 改为精确相对文件白名单；active providers.json 由公开 example 生成，example 必须全 disabled，在写 ZIP 前检查；非标准未知文件不进包。最小测试夹具可缺少其他白名单文件，延续旧发行测试合同；完整正式包独立核对全部白名单存在。白名单不能识别被人为写进已允许源码/文档/example 的秘密，仍需发布内容审查。

旧正式包 SHA256=7bc397accfc734d00c61f37103b39870ce15b14486e25a89663600b8d1da2eec，66 条目，manifest 哈希一致，active config=example，供应商全 disabled，未命中敏感路径。结论是本次没有发现实际泄露证据，不是保证不存在任意未知形态的秘密。Git 旧忽略规则会暂存部分 config 备份/log/db；现规则覆盖非公开 config、备份、日志与 DB。任意名称如 tokens.txt、写在源码中的秘密、已有 tracked 文件仍需审查。公开发布另需清理/泛化历史文档个人绝对路径；本轮为保存历史证据未大规模改写这些资料。

### 多窗口 Key

`routes.save_key` → `ConfigStore.save_key` 在 settings_lock 内验证 provider/revision、读最新 secrets 并修改单个 provider 后原子写。同身份同配置 revision 先后保存同一家的 Key 允许最后写入者生效；配置 revision 不因 Key 更新变化。并发修改不同家的 Key 不丢其他条目；环境变量优先。身份配置变化后旧窗口 409；兼容脚本省略 expected_revision 是明确按当前 ID 写入，不能据此声称提供旧窗口 CAS。

本轮并发/真实 route 回归验证上述合同，REJECTED 将普通最后写入称为缺陷。未添加凭据版本、未改秘密指纹与恢复。身份变化/新 Key 不允许错误拼接旧受理端点；显式保留 ID/Key 迁移地址依旧合法，不自动清 Key。

## 新确认的问题与拒绝修改项

非法 multipart image_field=42、[]、{} 在原版本可以保存，HTTPX 本地构造出错被宽泛分类为 transport_uncertain。实际 POST 为 0，却锁 nonce、保留 0.1 费用且不尝试备用；空名/控制字符也可能构造出错误字段。CONFIRMED。新增 `_multipart_field` 在使用 image/mask/upload 字段时要求非空字符串且无控制字符/DEL，抛 safe_to_failover 的 APIError；没有 provider_failure，故主家不冷却。合法 image[] 保留，发送后的不明异常仍保守停止。

修复后捕获只 POST backup，status=success，主家健康，主家预留释放、仅备用费用保留。见 reproduction-after.txt、test_round5_contracts.py、targeted-final.txt。

“鉴权头名称未校验”的额外猜测 REJECTED：`validate` 已有 `[A-Za-z0-9-]+` 正则，整数、对象、布尔、空白、换行、冒号、中文在配置保存前拒绝，配置不变、无 HTTP。auth-before.txt 本来就通过，不能伪装成 RED。未修改这部分生产代码。

Windows 存储异常已观察到，但根因 UNVERIFIED。未增未经证实的重试；未改调度器、账本 schema、nonce/fingerprint、恢复、节点端口、工作流、依赖、许可证、图像尺寸或背景融合业务。

## 历史修复逐项复核

| 旧问题 | 当前源码判断与本轮执行证据 |
|---|---|
| 模型选择关闭自动路线；旧能力/参数残留 | 前端选择模型只更新映射，保留 auto_failover；新映射不继承旧报价/能力。四套 JS 合同及 round2/3/4 前端测试 |
| IMAGE/MASK 漏映射 | Protocol.submit 在上传/编辑前按完整值集合校验；缺 mask、多图单值、无 image 明确失败。round3_protocol、round5_contracts |
| 本地配置错误冷却 | safe_to_failover 与 provider_failure 分离；本地模板、auth、pool/deadline 无错误冷却；实际连接失败/已配置明确拒绝仍冷却。round4_health、round3_state |
| 新供应商旧 Key；端点/Key 不一致 | 前端新 ID/空 key_env；ConfigStore.credential 一致身份捕获。round4_credentials 和前端合同 |
| 异步凭据错配/旧记录 | 凭据 hash 非原始 Key；已变身份需匹配原 Key，legacy 无 hash 更保守；同身份轮换允许；持久内联/匿名结果不强制 Key。round4_credentials/recovery |
| 费用/币种/nonce | 历史币种保留；零价格累计不阻断后续有限预算；未知价在有限额下不提交；同 nonce 复用原意图，改变 nonce 才新任务。round2_scheduler、round3_state |
| 并发恢复覆盖完成 | Journal.mark 保护完成终态，晚到 success/failure 都保留完成缓存。round2_scheduler 的真实 HTTP 并发测试 |
| 重复收费/受理未知 | 原主家 uncertain/accepted 不发备家，保留预留；并发相同指纹仅一次提交。round3_state、round4_health、round2_concurrency |
| 时间预算 | 初始化/上传/轮询/下载/连接池不能重启预算；流式响应受 deadline/大小限制；不是毫秒级强制抢占。round2_scheduler、round3_protocol |
| 缓存配置阻拦 | 完成缓存优先于新候选/凭据检查；基础 cfg.load 仍必要，坏配置不保证离线读取。round4_recovery、round3_state |
| JSON 参数/旧配置 | 非对象 false、0、[]、字符串拒绝；None/{} 正常；历史 config/legacy 任务依旧走现有合同。round4_parameters、config/credentials 测试 |

以上关键回归在最终 154 项源码全套中执行，不仅引用历史报告。没有观察到因本轮最小逻辑修改导致的新增业务回归，但无法从 Mock 或重跑通过证明目标平台所有条件均稳定。

## 真实测试记录

| 运行 | 结果 | 原始日志（上级 audit-round5） |
|---|---|---|
| 原始 0.1.3 全套 | 143 total / 142 pass / 1 Torch skip / 0 error | baseline-python.txt |
| 新增合同原版 RED | 初始 6 方法，8 subtest failures | contracts-before.txt |
| 新增发行原版 RED | 2 failures；未知文件已写入 ZIP | release-before.txt |
| 第一次修改后全套 | 152 total / 149 pass / 1 skip / 2 Windows errors | source-python.txt |
| 同源码新鲜重跑 | 152 total / 151 pass / 1 skip / 0 error | source-python-rerun.txt |
| 两个受影响测试各 10 次 | 20 total / 19 pass / 1 Windows error | storage-recheck.txt |
| 新增最终针对性回归 | 11 方法全部通过 | targeted-final.txt |
| 最终源码全套首次 | 154 total / 152 pass / 1 skip / 1 Windows error（providers.json） | source-python-final.txt |
| 白名单历史报告条目修正后源码全套 | 154 total / 153 pass / 1 skip / 0 error | source-python-delivery.txt |
| 原始最小复现修复后 | 2 方法全部通过，无未知文件进 ZIP、仅备用 POST | reproduction-after.txt |
| 保留未改行原始换行后的最终源码 | 154 total / 153 pass / 1 skip / 0 error | source-python-preserved.txt |
| 最终字节候选包全套 | 154 total / 153 pass / 1 skip / 0 error | package-python-preserved.txt |
| 源码四套 JS | 全部通过；review 15/15，round3/4 各 6 场景 | source-test_frontend*.txt、source-test_round3/4_frontend.mjs.txt |

第一次 Windows 异常分别来自 round3_routes Key presence 与 round4_health setUp；最终首次来自 test_engine 的配置保存。共同栈是 config.atomic_json → os.replace → WinError 5。记录失败与绿色重跑并列，不删除原始证据。1 项真实 Torch skip 不计通过；替身张量/HTTP/前端合同不能替代真实 Torch、浏览器和完整 ComfyUI。

## 最终发行包验证

保留未修改行原始换行后，最终候选包解压至独立 package-test-preserved-0.1.4，执行完整 Python：154 total / 153 pass / 1 真实 Torch skip / 0 failures / 0 errors，退出 0，日志 package-python-preserved.txt。四套 JS 均退出 0，日志 package-preserved-test_frontend.mjs.txt、package-preserved-test_frontend_review.mjs.txt、package-preserved-test_round3_frontend.mjs.txt、package-preserved-test_round4_frontend.mjs.txt；preserved-test-exits.json 保留每套退出码。

34 个 Python 文件 AST 解析通过，前端模块 node --check 通过，mock CLI 仅绑定 loopback、短时运行退出 0。实际环境 Python 3.12.14、HTTPX 0.28.1、Pillow 12.3.0、aiohttp 3.14.4、NumPy 2.3.5，无真实 Torch；见 syntax-environment.json、mock-cli.txt。这些版本是本机实际安装结果，不是供应商或 RH 的支持声明。

测试后仅补齐本报告的真实包内结果，重新构建最终 ZIP；所有 .py/.mjs/.js 执行代码与先前解压回归包逐字节一致，最终 ZIP 再次独立核对 CRC、精确文件集合、每项 manifest 哈希和当前源字节。白名单 68 项、生成的 active config 与 manifest 共 70 ZIP 条目；manifest 描述 69 项，self manifest 不自哈希。active config 等于公开 example、四家均 disabled。完整记录见 package-verification.json；最终 archive hash 由根 DELIVERY.json 和 releases/SHA256SUMS.txt 提供，避免报告把自身包哈希写入造成循环。

实际源目录经项目 work 下独立 Git index 暂存，69 个文件，未发现白名单外路径，未暂存 private/active config；文档仍有 13 处个人绝对路径，见 git-publication-review.json。未创建远程或推送。这是当前暂存候选的内容边界检查，不能保证未来任何新增文件/修改都会无秘密。

关键新增定位：protocol.py 的 `_multipart_field` 第 53 行、submit 第 161 行；engine.py 的 edit 第 50 行、恢复 warnings 第 83 行、当前候选警告生成第 146 行；config.py 的 save_key 第 220 行、settings_lock 第 37 行；发行精确白名单见 build_release.py 的 RELEASE_FILES 和 build。

## 最小变更、原件与交付可追溯性

修改生产代码仅 engine.py、protocol.py、build_release.py；附加 .gitignore、版本、必要 README/合同/验证文档、新增两个测试文件。新增的 newline-preservation.json 记录了五个修改文件未改行的原始换行恢复；逻辑内容未改变，并对最终字节版本重新全套回归。已有测试、配置模板、依赖和节点/工作流字节保持原样（最终差异清单独立核对）。发行白名单误将 ROUND4 替换为重复 ROUND5 的本轮中间修改已修正，历史报告重新入包；正式包在修正后构建并回归。

原件 original-0.1.3.zip 的 SHA256 为 8b985406af4dc028a0a497b7b69180e535c1fd581944a0e559a02958a9b9c99b；original-hashes.json 记录逐文件哈希，根 README/DELIVERY 原件也保留。最终 CHANGES.patch、CHANGES.json、final-hashes.json、test-summary.json、package-verification.json 和根 DELIVERY.json 描述实际交付；SOURCE-MANIFEST 只描述包中文件，不假装构建器执行过测试。旧 0.1.3 ZIP 保留。

## 用户十二问的直接回答

1. **0.1.3 历史修复是否确实完成？** 上表所列关键行为在源码及本轮测试得到支持；没有把旧报告或绿色计数当证明。Windows 文件替换历史异常再次复现，仍未解决，不能说全部稳定。
2. **三组疑问裁决？** 模板常量合法 REJECTED 强制改写，未映射报告缺说明 CONFIRMED；递归打包风险 CONFIRMED、旧正式包实际泄密无证据；同身份同 revision Key 最后写入 REJECTED，跨供应商丢失更新未复现。
3. **进一步业务 Bug？** 非法 multipart 字段本地构造错误被当作付费未知 CONFIRMED，已修；Windows 存储拒绝访问复现但根因 UNVERIFIED；鉴权头名称猜测 REJECTED。
4. **Python/JS/依赖/注册缺陷？** 没发现新增语法/注册/前端合同缺陷；声明 Python>=3.10，HTTPX/Pillow 为直接依赖，NumPy/Torch/aiohttp 来自 ComfyUI，开发环境另列依赖。只实测本机 Python 3.12 与安装依赖组合；未证明所有版本/完整宿主兼容。
5. **已修复哪些？** 精确发行白名单+禁用前置检查+Git 排除；multipart 字段先验分类；JSON 映射报告警告与恢复保留。版本同步 0.1.4。
6. **拒绝哪些修改？** 强制文本占位符、给 Key 单独并发版本、每次改 URL 清 Key、改变 nonce/账本/受理后自动切换、擅增背景局部合成、未经根因证据的存储重试。
7. **是否有修复新回归？** 没发现新业务逻辑回归，白名单历史报告条目中间失误已修。全套曾报 Windows 存储 errors，最终通过不能抹去它们；真实平台回归仍待验。
8. **调度/隔离/恢复/防重复是否仍正确？** 已有契约内源码和 HTTP/并发回归支持；accepted/unknown 不再 POST、身份/Key 快照、原任务 GET 恢复与费用预留保留。前提是正确配置、持久同一账本、单一一致部署；不等于远端 exactly-once 保证。
9. **是否符合灵活更换中转目标？** 对现有 multipart/JSON、配置鉴权、可选模型发现、上传/GET 异步协议符合，主+3备可扩展，手填模型支持。不是任意 URL 万能；HMAC/WebSocket/专有登录等需网关或明确新增适配，模型能力/价格不能靠名称推断。
10. **普通 ComfyUI 可否受控安装？** 可以按 README 安装本 ZIP，使用 ComfyUI 自己的 Python 和免费 loopback mock 开始受控验收；本轮没有完整宿主/Torch/浏览器成功证据。先核节点注册、端口、管理界面、IMAGE/MASK tensor、nonce 缓存和 Windows 配置保存。
11. **GitHub 可否上传？** 插件目录可作独立私有开发仓库，先检查实际暂存和排除秘密/运行数据；公开开发仓库还需人工审查允许文件内容、泛化个人路径并核对许可证。上级审计/研究/work 不上传，未执行远程推送，当前不可宣称生产稳定版。
12. **距大陆 RH/生产还缺什么？** RH 收录或私有安装权限、前端/路由支持、目标域名/CDN出站与认证、租户秘密隔离、持久共享账本/重启并发条件和实机执行；供应商正式编辑/发现/上传/Mask/参数/异步/计费/幂等合同，以及有授权的真实输入输出质量/账单/故障恢复验收。需解决目标 Windows 存储不稳定并补真实 Torch/ComfyUI、大图资源与预算压力测试。

## 实机验收与联网证据界限

建议顺序：普通 ComfyUI 免费 mock 验收 → 根据供应商正式文档配置一家同步或异步图像编辑 → 在明确付费授权后执行一笔并保存实际模型/MASK/输出尺寸与账单 → 验证已受理断连和相同 nonce 恢复 → 逐家接入备商 → RH 权限/网络/秘密/持久化审查后独立实机验收。没有默认调用付费接口。输出保留 API 实际尺寸；Mask 不是像素级硬保护，适配器不添加背景合成业务。

本轮通过 web 工具尝试 SubRouter models 指定页面、官方 ComfyUI 自定义节点资料和 RH 定向检索，未得到可用页面内容或足以确认当前部署的可靠返回；这不能支持当前商家或 RH 已接通。历史 RUNNINGHUB、GATEWAY 等文档的引用仅保留为历史，不冒充本轮重新验证。SubRouter 不是写死供应商，未因无法访问而虚构编辑请求、模型能力、价格或云端政策。联网未补齐的信息列为 UNVERIFIED。

许可证原文保留：自有 MIT，HTTPX BSD-3-Clause，Pillow MIT-CMU；本轮不新增第三方代码或依赖。四个指定 Skill 的已读取流程落在原件备份、源码追踪、RED/GREEN、最小修复和真实限制记录上；不重复声明历史“外部审计”足以代替取证。

完成本轮后停止，等待下一步指令。
