# H3 通用 API 适配器第五轮补充独立审计（0.1.4 → 0.1.5）

日期：2026-10-11，Asia/Shanghai。基线是本轮原始备份，不依赖历史报告的判断。0.1.5 是开发验证版本，尚不标为生产稳定版。所有业务请求均为本机免费 Mock，全部 Key 为合成假值；未调用收费服务、未执行 RH 云端任务、未推送 GitHub。

本报告随节点分发；完整原始日志、TCP 捕获、ZIP 哈希、差异与最终验收摘要位于交付项目的 `audit-round5-followup-20261011/` 和根 `DELIVERY.json`。这些环境证据不进入插件 ZIP。历史 0.1.4 包、源码原始备份与旧审计证据保留。最终 ZIP 的实际测试状态以 `test-summary.json` / `package-verification.json` 为准，构建脚本不会自行宣称执行过测试。

## 1. 实际版本与范围

原始正式 ZIP SHA256：`01125f0dea4b024254db79ef85c2ad8d7701420971c5e786f6a4d40fb8f75fc5`。另建 `original-source-0.1.4.zip` 和逐文件 `original-hashes.json`。审计范围是整个独立插件：入口、节点、config/engine/ledger/protocol/routes、完整管理前端、构建与 Mock 脚本、公开配置和工作流、依赖、发行/忽略规则及测试。生产代码最小修改集中在 `h3_adapter/config.py` 和 `web/h3_adapter.js`，另同步版本、必要测试、验证脚本和文档。调度器、协议层、账本、节点端口、工作流及配置例子的可执行内容未重写。

使用并完整读取用户指定的全局看代码逻辑、调Bug、省代码总规则与联网资料过滤器 Skill。最后一个文件实际是 AnySearch 使用指南；没有提供其 Key，故未安装未知远程脚本，改用官方公开页面只读获取和真实浏览器渲染。代码索引返回无关项目，未把其结果作为源码证据。

## 2. 已读模块与业务调用链

逐段读取全部生产 Python、前端及构建/Mock 脚本，检查公开配置、依赖、管理权限和相关回归方法；所有 Python 测试文件都经语法/方法清单扫描并实际执行。没有把运行测试声称为逐行读完每篇历史说明。

`__init__.py` 注册节点/WEB_DIRECTORY/管理路由 → `nodes.png_inputs` 编 IMAGE 和白色可编辑 MASK → `Engine.edit` 校验、指纹与 `Journal.begin` → 已完成缓存/不明状态阻止重提/已受理恢复 → 供应商能力与优先级筛选 → `ConfigStore.credential` 原子捕获身份和 Key → `Journal.reserve` 费用预留 → `Protocol.submit` 单次 POST → 落盘 accepted/result_ready → `Engine.recover` 只 GET 原任务/下载 → Pillow 校验/结果缓存 → 标准 Torch IMAGE。账本以 SQLite BEGIN IMMEDIATE 保护任务领取及预算；新模型需要新 nonce 才表示新的付费意图。

管理链：真实前端 DOM → `routes.authorize` 本机或管理员令牌/Origin 检查 → ConfigStore 跨进程锁 → revision 比较/原子替换；发现模型仅获取 ID，不能证明模型能力或自动价格。

## 3. 外部疑问成立项（CONFIRMED）

| 问题 | 独立证据 | 最小修复 |
|---|---|---|
| A：JSON 序列化、fsync、replace 失败后残留包含假 Key 的 tmp | `contracts-before.txt` 的失败断言及修复后三个失败注入测试；最终文件旧字节完整 | `atomic_json` 用 finally 删除自身唯一 tmp，仍抛出原失败，不将半写入视为成功 |
| B：保存删除 A，再用同 ID 新建 B，会把 A 的文件 Key 发给 B | `merchant-reuse-before.json` 实际 `/old/images/edits` 和 `/new/images/edits` 都携带旧假 Key | 保存删除时先退役 Key、清空活动绑定并增代次；新身份必须设置新 Key，旧凭据按任务指纹供历史恢复 |
| 同配置删除/重建形成 ABA：旧窗口 revision 再次匹配，可回写旧 Key | `stale-window-before.txt`：同 URL/ID/其他配置完全还原后旧 Key 保存原本未拒绝 | revision 纳入本 ID 的凭据解绑代次；保存返回 revision 和 public 快照在现有锁内 |
| Windows 适配器自有读取与 os.replace 竞争 | `internal-reader-before.txt`：真实读取句柄被保持，另一线程保存触发真实 WinError 5 | `load` 共用 settings_lock；锁内调用 `_load`，避免 Windows 字节锁重入；没有添加重试 |

11 个针对性合同测试通过，包含不同 URL、相同 URL、旧任务恢复、旧窗口保存、 legacy 快照和“退役秘密已成功、发布删除配置失败”边界。后一情况保留原配置和退役凭据、阻止新提交，旧 paid task 可恢复；不是跨两个文件的事务性全成功，失败后应重新读取配置确认。

## 4. 明确拒绝修改（REJECTED）

合法 JSON 常量模板仍属现有合同；保留未映射警告，不强制改成动态占位符。同一个持续存在的身份只更新 Key，允许后写覆盖先写；不让 Key rotation 改变解绑代次。保持 ID 连续存在而明确编辑 URL 仍是允许的网关迁移，文件 Key 不自动清除。环境变量是用户明确声明的外部绑定；同名变量的显式复用不偷偷删除。新增 UI 供应商默认禁用、清空 key_env，以避免无意绑定。

一次最终 JSON 保存中“删除又加回相同 ID”没有可观察的删除事件；无法推断用户未保存的中间操作。nonce 缓存保留原付费意图是正确合同，配置模型改变不能在同 nonce 下偷偷重新收费。接受状态未知/5xx/响应读超时不得为方便主备切换而重 POST。终态远程失败也不另开备用任务。现有默认 result 路径只取第一张，不编造多结果输出支持。

## 5. UNVERIFIED 及尝试

历史随机 WinError 5 的每次具体占用者未取得事发时进程/句柄证据；已证明可致同类错误的机制，但没有据此断言全部历史故障同源。外部编辑器/杀毒/同步工具持有不共享删除的句柄仍可拒绝保存。进程强制终止或文件系统拒绝 unlink 时无法保证 finally 清理；真实共享文件系统的锁/fsync/SQLite 行为未测试。

真实商家受理语义、图像编辑效果、账单、限流和 SLA 未验证。RH 无登录安装权限与免费云端条件；官方页面只读调查不等于实机成功。最低声明 Python 3.10 的独立完整环境未另装；本轮实测 Python 3.12.14。针对公网/共享多用户管理部署仍须配置服务器认证、目录权限和数据隔离。

## 6. 历史修复回归

旧 154 项 Python 回归保留，并运行四组 JS。独立检查：选择模型不关闭 auto；新 ID 清除旧能力/价格/默认参数；multipart 与 JSON 本地非法输入在发送前识别、健康主家不冷却；警告随缓存/恢复保留；result_ready 不被过期 Key 阻断；未知/受理/已完成状态不重 POST；并发预算预留与相同 nonce 单领取；旧 task 使用快照 URL/模型；模型发现失败可手填；精确发行白名单排除未知秘密/备份；前端异步结果不会写入已切换身份。没有以历史报告代替这些执行断言。

## 7. 主动发现的新增问题

除了用户提出的 A/B，本轮确认相同配置的 ABA revision 和 Windows 内部 reader/writer 冲突，均先 RED 再 GREEN。没有找到需要重写 scheduler/ledger/protocol/nodes 的新证据。原始失败日志和测试夹具自身错误保留；不存在为把测试染绿而改核心付费规则。

## 8. 修改与可追溯差异

`CHANGES.patch`、`CHANGES.json` 和 `final-hashes.json` 给出相对于本轮原始源码的精确文件变化。保留未修改行的原换行字节；文档中个人路径泛化仅用于公开发行，原始文档仍在原始备份。`SOURCE-MANIFEST.json` 逐项记录 ZIP 内公开内容哈希；活动 providers.json 唯一允许差异是替换成禁用 example。新增独立脚本 `scripts/independent_http_smoke.py`，不调用既有 Mock/test fixture。

## 9. 语法、依赖、真实宿主

Python AST/compile、JSON 解析及 JavaScript module syntax 单独检查，完整回归另保存日志。真实 CPU Torch 2.14.1+cpu / torchvision 0.29.1+cpu / torchaudio 2.11.0+cpu 可导入；pip check 无依赖断裂。并非宣称未来所有版本组合兼容。

从官方 ComfyUI 克隆 commit `0df64eb242b7c5759c3e86afd5d1846d923b1033`，前端 1.55.14，独立 venv、custom_nodes、input/output/user/config/runtime；`--cpu --offline --disable-assets`，未下载模型，也未改现有生产宿主。GPU 不属于本轮所需闭环。

## 10. 调度、Key、nonce、费用与恢复

四家 A→B→C→D 明确拒绝后成功；所有家明确拒绝返回失败而不伪造输出。已受理/未知不切备用；连接前失败可换、响应超时不可换。能力/参数非法先筛选；未发 HTTP 不冷却。删除重建旧 Key 仅用于原 fingerprint 的恢复，新请求无活动 Key 就不发。连续同身份 Key rotation 合同仍保留；同时改 Key+URL 会阻止旧任务查询，不重提。

旧平面字符串 secrets 与旧账本仍可读；退役发生后没有 fingerprint 的 legacy 任务不能安全判定凭据，因此保守阻止，需人工确认原身份，不能自动猜测或重新付费。不要把新 secret 对象结构直接降级给旧版本当作兼容保证。

费用为用户声明币种的保守估计/持久预留，不是供应商真实账单或退款证明。配置需统一币种，不能把 USD 和 CNY 数字混用；拒绝可释放，受理/未知预留保留。相同 nonce 不因修改 timeout、Key、报价或模型映射而新收费；新付费任务增加 nonce，避免误以为修改配置即可拿新结果。

## 11. 新独立 HTTP 冒烟

新 stdlib ThreadingHTTPServer + HTTPX 真实 TCP，27 类：实测 multipart model/prompt/双图/mask；JPEG 与不同尺寸；两个结果按显式第一项取图；401→备；401/403/404→第四家；全部拒绝；受理后坏 JSON、截断、无结果、坏图片；响应延迟超时；NaN 与非法 multipart/未映射 JSON 本地失败；合法常量警告；真实 connection refused；连接超时注入（明确不是实际公网 ConnectTimeout）；异步受理/重启/快照/缓存/新 nonce；改 Key+URL 禁止污染恢复；六线程同 nonce 一 POST；六个不同 nonce 共享 .1 预算一 POST；发现模型与付费意图；实际 HTTP503 不切备；未知 async 状态 pending；终态失败不重提；mask 不兼容先排除；alpha→灰度编码。捕获请求和 SQLite 行保存在 source/package independent HTTP JSON。

## 12. Windows WinError 5 的可信原因

`windows-evidence.json`：只读目标实际 WinError 5；CreateFileW 使用 SHARE_READ|SHARE_WRITE 而无 SHARE_DELETE 的实际句柄也导致 WinError 5；CloseHandle 后同操作成功。无 reader 300 次 atomic 写入零失败；未加锁普通 Python reader 参与 300 次写入有 279 次写错误和 26 次读错误，最终 JSON 完整且无 tmp。此受控外部 reader 实验不是被修后的 ConfigStore 内部调用。

内部真实句柄 RED/GREEN已直接证明源码冲突；修复后 `windows-store-stress.json` 的 save/load/public 各 300 次并发操作均零错误、无 tmp。双独立进程 save_key 保留两个 Key，陈旧 revision 被拒。ACL 用 icacls 留证；Windows chmod(0600) 不等于证明 Unix ACL 隔离。load 现在需要可创建/写入同级 .settings.lock 的目录；只读挂载不作为已验证部署模式。

## 13. 普通 ComfyUI 的实机结论

已在实际官方宿主执行 LoadImage→H3ImageEdit→PreviewImage/SaveImage，分别有/无 MASK；验证输出实际尺寸 11×5、RGB 像素 (13,173,97)，白色 MASK 发给 API 的 alpha 为 0。注册通过 object_info，WEB_DIRECTORY JS 内容与源码逐字节相同。五次队列：无 mask、新 mask、同 nonce、重启同 nonce、新 nonce，只有三次 Mock POST；同 nonce 在宿主重新启动后从磁盘缓存取图。

真实 Chrome 独立 profile 的 DOM 操作通过：创建真实注册节点、打开经理、新增禁用供应商、应用/保存配置、假 Key 保存后清空且不回读、固定/auto 切换、手动发现模型、换模型重置能力报价、保持 auto、序列化无 Key。节点创建和打开入口通过真实 app/LiteGraph 回调，随后按钮和表单用浏览器点击/填写，不声称已测试所有画布拖拽交互。截图和 browser-evidence.json 保存。初次测试过早导入 app shim、标签名称写错的夹具失败保留，修正测试后通过，没有修改宿主或产品代码来绕过失败。

## 14. RH 已验证与未验证

2026-10-11 重新只读取得 RunningHub 中国站任务 API、工作流接入示例和其官方 OpenAPI 插件 README（HTTP200，原文与哈希保存 official-current）。官方任务文档是调用已有工作流/传图/节点参数及查询结果的依据；不构成安装任意 Python custom_node、任意 HTTPS 出站或用户私有秘密存储的许可证明。RH 官方本地 API 插件的环境变量/.env说明也不证明托管工作台拥有同等能力。

RH 节点收录/安装、本插件 WEB_DIRECTORY 加载、出站目标与 Authorization、租户私密 Key、跨重启 runtime、共享存储锁/SQLite，全为 UNVERIFIED。没有 RH 云任务成功记录。

免费最小验收顺序：平台确认/安装该版本并取 object_info；禁用收费供应商、配置可控免费 HTTPS 假服务和独立假 Key；检查 JS/管理员认证；执行有无 mask并读取Preview/Save；相同nonce只一POST；服务重启继续缓存/accepted task GET恢复；两 worker共目录并发nonce/预算检查；验证目录与账本跨容器重启存在且对他人不可读。RH 即使模型Mock免费也可能收云运行费，无平台免费条件时不得自行发起。

官方来源：
- https://www.runninghub.cn/runninghub-api-doc-cn/api-425749013
- https://www.runninghub.cn/runninghub-api-doc-cn/doc-8287342
- https://github.com/HM-RunningHub/ComfyUI_RH_OpenAPI
- https://docs.comfy.org/custom-nodes/walkthrough
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew

## 15. SubRouter 或真实中转还缺什么

同日读取 llms.txt、docs、models并用浏览器渲染模型文档标签页。公开默认示例是 Chat Completions；模型专属文档所查标签显示暂无可用模型。不能把“OpenAI兼容/模型市场有名称”当作 image edits + mask 成功。站点当前还显示大陆新增注册/充值/相关生成式AI服务的区域提示，这是当前公开页面观察，用户已有账户能力仍需本人确认；未绕过限制。

每个目标商家仍须提供实际编辑model ID、multipart/JSON或上传协议、mask语义、多图限制、认证/正式发现路径、async接受/成功/失败字段、结果下载主机与鉴权、明确不受理错误语义、统一报价。常规 multipart或声明式JSON/upload/poll模板可配置；Gemini原生复合内容/聊天视觉模型/供应商特殊签名或复杂预处理并非只改URL可支持，应以小的独立协议扩展加真实文档测试，不写死SubRouter。

公开来源：https://subrouter.ai/llms.txt、https://subrouter.ai/docs、https://subrouter.ai/models?page=1。公开资料及免费本地验证不等同商家已授权测试或真实模型出图。

## 16. 是否满足日常管理与图像编辑

普通ComfyUI中，添加商家、地址、独立Key、手填/发现/搜索模型、逻辑映射、primary+至少3 fallback、启用/固定/auto、IMAGE可选MASK、状态/实际供应商/耗时/费用估计已具备并完成本地真实宿主闭环。高级协议/能力/参数/报价仍需在管理JSON中明确填写，不是自动了解各商家的万能向导；错误细节来自脱敏状态码，不回显原商家私密正文。当前可开始受控免费验收与逐家商业接入，不能宣称特定商家或真人移除质量已过。

## 17. GitHub 私有/公开开发仓库

应只提交插件根目录。精确白名单、禁用示例、MIT与HTTPX/Pillow许可文件齐全；虚拟环境、克隆宿主、第三方研究快照、密钥与账本在外部证据目录，不分发。公开文档个人绝对路径改为通用路径，原始证据另保留。实际隔离 Git 暂存验证与内容扫描结果见 git-publication-review.json；完成该复核后可作为私有或公开开发仓库提交，不以.gitignore替代实际暂存内容审查，未执行push。

clone后的源码先复制 providers.example.json为providers.json（不得覆盖已有文件），用宿主Python安装requirements；独立开发回归另装requirements-dev、numpy，先建 ../work/tmp。免费独立HTTP脚本无需Torch；真实节点由ComfyUI依赖提供Torch/NumPy/aiohttp。ZIP使用同一源码白名单，活动配置替换为禁用example，逐字节等价/CRC/manifest与最终解压回归另留完整记录。

## 18. 距生产的真正阻塞项

特定真实供应商的协议/模型能力/安全拒绝语义/报价与受控真实效果账单验收；目标宿主权限与磁盘持久性；Windows外部句柄或权限导致的替换失败仍需目标机器长期观测；公网/多租户的管理认证和私密目录权限；RH的安装/网络/前端/持久化/共享锁实际验收。上述未完成前不标生产稳定版。不需把H3、分割、背景融合、Z-Image功能塞进本适配器。

本輪完成可执行免费工作后停止；后续真实Key/收费/RH任务须由用户另行授权。
