# H3 API + A2 BackgroundBridge（单仓库集成）

**当前版本 0.1.7，2026-10-13。** 同一插件目录注册 H3ImageEdit 与全部七个 H3A2 Bridge 节点，保留 API Key、Base URL、模型、主备、请求账本及 **H3 供应商 / 密钥**、**H3 搜索 / 选择模型** 两个入口。既有 H3 Core、Qwen/Z-Image 等依赖仍须安装。见 [RH 安装说明](docs/RH-INTEGRATED-INSTALL.md)、[两轮独立取证与测试](docs/AUDIT-017.md) 和 [121 节点 / 251 连线示例](workflows/H3_A2_API_ZImage_BackgroundCache_INTEGRATED.json)。

本版修复未使用备用配置造成重复 POST、共享账本结果授权、未证明账号的 Key 恢复、压缩响应提前解压、独立标准图像消费者失败输出，以及 Finish 先写 READY 后检查证据。Bridge Prompt 仅保留编辑原文；请求身份、凭据代次、账本和六源码 SHA256 校验继续启用。

免费验证：Python 192/192、前端 6 套、真实 TCP Mock 27/27、实际 ComfyUI 八节点加载、真实 Core/Bridge 11/11、真实调度 22 场景符合预期。Qwen/Z 是 CPU 替身，H3 是输入边界观察；真实供应商、生成质量、正式视频及 RH 未验证。当前为经本地审核的插件候选，不能据此声称云端兼容或生产验收。

## 1. 安装到自己的 ComfyUI

1. 解压交付 ZIP，将 `ComfyUI-H3-Adapter` 文件夹放到你自己的 `ComfyUI/custom_nodes/`。
2. 用 **ComfyUI 自己的 Python** 安装 `requirements.txt`，不要用系统另一套 Python。例如 Windows portable：
   ```powershell
   .\python_embeded\python.exe -m pip install -r .\ComfyUI\custom_nodes\ComfyUI-H3-Adapter\requirements.txt
   ```
   普通虚拟环境：`python -m pip install -r custom_nodes/ComfyUI-H3-Adapter/requirements.txt`。
3. 重启 ComfyUI。添加 `H3/API → H3 Universal Image Edit / 通用图像编辑`。
4. 导入 `examples/image_edit_minimal.json`，在 LoadImage 选择自己的输入图片（或上传 `examples/example_input.png`），暂时不连 MASK。
5. 点击节点 **供应商配置 / 密钥**。只管理本插件配置，不安装/修改其他节点。

**Git clone / GitHub「Code → Download ZIP」源码安装：** 发布仓库根应是 `ComfyUI-H3-Adapter`（直接包含 `__init__.py`），不要提交上级交付目录的 `work/`、研究快照或审计临时文件。源码不会包含被 Git 忽略的个人 `config/providers.json`；正式 Release ZIP 则已放入禁用供应商的占位配置。完成源码复制和依赖安装后，先在插件目录执行以下首次初始化，再重启 ComfyUI：

```powershell
if (-not (Test-Path -LiteralPath .\config\providers.json)) {
    Copy-Item -LiteralPath .\config\providers.example.json -Destination .\config\providers.json
}
```

Linux/macOS 在插件目录执行 `test -e config/providers.json || cp config/providers.example.json config/providers.json`。这些命令不会覆盖已有配置；不要取消 active config 的 Git 忽略规则。`.env`、`*.env`、私密 runtime 和 SQLite 伴随文件也不能提交；忽略规则不能清除已追踪文件或替代账户权限。若设置了 `H3_ADAPTER_CONFIG` / `H3_ADAPTER_RUNTIME`，密钥保存在实际配置路径的同级 `secrets.private.json`，实际 runtime 路径也须单独保护和排除分享。

要求 Python >=3.10；HTTPX/Pillow 为直接依赖；NumPy/PyTorch/aiohttp 使用 ComfyUI 现有依赖，不额外装 GPU 框架。管理前端基于官方传统 extension API；实际 RH 前端是否加载插件另行验证。

## 2. 填四家供应商（全部是占位模板，不是已开通商家）

`config/providers.json` 已有 primary、backup1、backup2、backup3，默认禁用且价格未知，防止误发。对每家：
- 填准确 `base_url`，包括供应商需要的 `/v1` 前缀；`edit_path` 会直接附加，不会偷偷再加 `/v1`。
- 填 `protocol` / `edit_path` / `request` / `result`，依据这家的正式文档。兼容图像 API用 `openai_images`；其他 JSON/上传/异步 HTTP API参考 `config/protocol-variants.example.json` 与 `docs/PROTOCOLS.md`。
- 在 `models.background-edit.id` 填真正的**编辑模型** ID，声明 `task=image_edit`、`supports_mask`、`max_images`、`allowed_params`、`defaults`、保守 `price_upper_bound`。
- 报价统一到配置 `currency` 单位；填完地址、能力和估计后 `enabled=true`。
- 用独立密码输入框保存 Key，或在 ComfyUI **服务器进程**设置 `key_env` 指定的环境变量。环境变量优先于私密文件。
- `primary` 指定主家；`fallbacks` 指定备家；备用先按 `priority` 升序，值相同时保持 fallbacks 顺序。主家始终优先。`enabled=false` 是长期/手动临时禁用；失败自动冷却 `cooldown_seconds`。

可添加更多 providers，不复制节点。Key 不存在节点 INPUT_TYPES，不写分享 JSON、非秘密配置或错误日志；管理接口只回布尔“是否已有”，没有 Key GET。

新增按钮生成新的随机 ID，`key_env` 留空，避免复用主商环境变量或已删除商家的私密 Key。可自己填写独立环境变量名；保存删除后再复用 ID 属于新的凭据绑定，文件 Key 不继承；退役 Key 只用于带原指纹的历史任务恢复。环境变量名仍是显式外部绑定，删除供应商不会删除服务器环境变量。保留 ID/Key 只改地址仍是允许的网关迁移配置，并不自动清 Key 或绑定域名；请确认新地址是你要发送该凭据的服务。

先应用并保存供应商身份配置，再保存 Key。当前管理界面附配置 revision；身份配置已变化时，旧窗口保存返回 409，不会覆盖新身份的 Key。同身份、同 revision 的 Key 更新按最后写入者生效，跨供应商更新由同一锁保护；未应用身份表单/未保存 JSON 也不发 Key 请求。兼容的脚本接口允许省略 `expected_revision`，表示按**当前** ID 写 Key，不具备旧窗口并发保护；脚本并发管理必须携带配置 GET 返回的 revision。

密钥文件 `config/secrets.private.json` 和请求目录 `config/runtime.private/` **绝不能分享/提交 Git**；runtime 包含私密图像/结果临时访问 URL。POSIX 文件权限 600/目录700；Windows chmod 不等于账户 ACL，服务器管理员必须用账户权限保护文件，不能让其他租户读取。不要把 ComfyUI 公网裸露，也不要把管理员令牌给工作流普通用户。

## 3. 模型发现、搜索、手填

点 **搜索 / 刷新模型**，选择供应商，刷新、搜索、选实际 ID，保存至逻辑模型映射。**模型列表只证明 ID 可见，不证明图像编辑/MASK/价格能力。** 保存选择不会伪造能力标记，也不会将 auto 隐式改成固定供应商。真实模型 ID 改变时，旧 mask/价格/默认参数/允许参数会清除，报价置为未知，需按正式 API 在供应商配置中重新确认；同 ID 保留已确认属性。费用上限不自动放宽。多窗口保存冲突返回 409，应刷新并合并后再保存，不要盲目覆盖。

没有正式模型列表接口时，保持 `discovery:null`；列表使用手动映射，同时可直接输入任意真实 ID。只有文档确认后才配置 `discovery.path/items_path/id_path`，路径可以不是 `/models`。本插件不抓目录页冒充 API，也不会因为发现失败阻止已配置模型运行。

`provider=auto`：选配置主备；手工填供应商 ID：固定该家，任何失败都不切换。`auto_failover` 节点/全局任一关闭都不切换。模型别名不同家可以映射不同真实 ID；只有明确满足 image_edit、MASK、多图、参数能力的家能备用。

## 4. 付费防重复提交规则（必须读）

- 没发送的连接失败、ConnectTimeout/PoolTimeout，或明确非受理的配置 4xx 拒绝，才可换家。默认仅401/403/404；429必须有供应商明确非受理证据才配置。
- POST 只发一次。读/写超时、断连、5xx、重定向、成功响应缺图/缺 task_id/解析失败：`uncertain`，**不再提交备用付费任务**。5xx不能配置成安全拒绝。
- 已收到异步 task_id：只 GET 查询同一家同一任务。查询/下载超时输出 `awaiting_result`；重新排队同输入/nonce只恢复查询或下载，不重发POST。远端终态失败也不自动新付费。
- SQLite 持久记录先占位再 POST；相同输入、prompt、逻辑模型、参数、固定 provider 和 `request_nonce` 形成稳定 ID。多进程争用也不能重复 POST；已完成结果从私密缓存返回。
- 想明确创建**新的付费编辑**才增加 `request_nonce`。换配置/Key/同一逻辑别名对应的实际模型 ID 不会自动重复既有已受理或完成任务：同一请求仍返回旧模型快照/缓存。希望用新映射重做时须明确改 nonce；新的输入/prompt/逻辑别名/固定 provider 模式本身也形成不同请求。不要删除账本或自动清缓存来强制换模型。
- `uncertain` 不能自动证明远端未扣费。先在商家后台查账/任务，确认后再由你决定新nonce。删除数据库、换runtime目录、换服务器或外部网关自身重试，都可能失去去重保护。本地请求ID不是商家保证的跨商幂等键。
- 支持 ExecutionBlocker 的 ComfyUI 中失败 IMAGE 会阻断标准 Save/Preview；文本/UI 状态报告保留。队列结束不等于 API 成功，应检查 status_report。独立库调用保留空 IMAGE 合同，不生成伪造背景。

0.1.7 在读取缓存与恢复前验证原凭据。相同 Key 可恢复；同账号换 Key 须在原任务受理前设置同一个非密钥 provider.account_id，且地址/鉴权身份与代次匹配。account_id 是管理员声明，不是账号验证服务；不同账号应使用独立配置/runtime/OS 进程。未证明账号时返回 credential_changed_no_resubmit，不查询旧任务、不自动 POST；恢复原 Key 后仍用原 nonce。内联结果、匿名下载与已完成缓存也须先通过账号授权。

升级账本保留原记录/任务/费用。含旧身份快照的账本遇到新的请求 ID 时默认阻断 legacy_journal_new_request_requires_review，防止旧 Bridge Prompt 更换后重复付费。先核对旧请求，确实允许新请求时由管理员设置 H3_ADAPTER_ALLOW_LEGACY_NEW_REQUESTS=1；不清空账本，不关闭版本校验。详见独立审计与 RH 安装说明。没有凭据指纹的旧快照无法自动证明账号，需人工核对；无共享持久 runtime 的多容器不能保证跨容器去重。

## 5. 超时、MASK、费用

节点 timeout 是整次调用预算（还受全局 timeout 上限和单家 timeout 限制）；异步另有有限 max_polls，没有无限循环。超时停止等待不等于取消云端任务。

固定模型/固定提示词 JSON 模板继续合法。未使用完整值 `{model}`、`{prompt}`，或有有效参数但未使用 `{params}` 时，`status_report.warnings` 分别包含 `json_template_unmapped_model`、`json_template_unmapped_prompt`、`json_template_unmapped_parameters`。`report.model` 是配置映射模型，不能据此认定固定模板的 HTTP model 与它相同。缓存与异步恢复保留这些提示；模板需按供应商合同设置。multipart 的 image/mask/upload 字段必须为非空字符串，不能含控制字符，非法值在发送前拒绝并可按设置尝试备用。

JSON 模板在任何上传/编辑 POST 前，按真正可渲染的完整值占位符校验实际 IMAGE/MASK：已连 MASK 却没有 `{mask_base64}` / `{mask_data_url}` / `{mask_ref}` 将明确拒绝，不伪报成功；多图需 `{images_data_urls}`。键名、字符串片段及 `{params}` 注入对象中的占位符不会再递归替换。仅模板实际使用引用时才上传，配置了 upload 不等于必须上传。字段的供应商语义仍须正式文档确认。

本地模板、非法鉴权、连接池等待与尚未发送的 deadline 错误可安全释放预留/按设置尝试备用，但不会误冷却健康供应商。真正连接失败和明确非受理的配置 4xx 保留冷却；已经发送/受理/不明的任务保留原有不再提交规则。参数必须是 JSON 对象；非法空列表、false、0、空字符串不再被当成空对象提交。

Comfy MASK 白色=要编辑，节点编码为透明 alpha=要编辑。模型可配置 `mask_encoding=grayscale_white_edit` 用白色灰度蒙版；不支持MASK的模型被排除，不静默丢MASK。必须由正式API说明确认能力；蒙版与首张图尺寸相同，一次一个MASK。LoadImage 对无alpha图片的默认64×64全零MASK不要直接接入。多图使用IMAGE batch，但只有配置max_images足够的模型才能调用。不会强行伪造局部修复/多图能力，也不添加未经要求的裁剪回贴链。输出使用 API 返回的实际尺寸，不自动缩放回输入；Mask 是供应商指导，不保证未遮挡区域逐像素不变。若业务要求硬性背景保留，应由独立背景处理模块定义对齐与合成。

`max_cost` 是本次请求保守估计上限，0禁止正费用；未知报价在有上限时不调用。`max_total_cost` 是这个runtime目录的累计**估计预留**上限；明确拒绝释放预留，已受理/不明/成功保留。价格来自你配置，不假设商家目录准确，不能保证真实账单不超限；需同时在商家账户设置硬预算。本插件不把不同币种混算，不导入旧账单或伪称实际成本。

## 6. 免费本地演示与测试

参见 `docs/TESTING.md`。简要：启动 `python scripts/mock_server.py --port 8788`；设置 `H3_MOCK_KEY=mock-only-not-a-real-key`，以及 `H3_ADAPTER_CONFIG` 指向 `config/providers.mock.json`；重启 ComfyUI再导入最小图。mock返回已知蓝色PNG，主p0默认401以演示切换到p1，**不是AI真人移除效果**。

本地纯调度测试：
```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node tests/test_frontend.mjs
node tests/test_frontend_review.mjs
node tests/test_round3_frontend.mjs
node tests/test_round4_frontend.mjs
node tests/test_final_frontend.mjs
```
需配置 TEMP/TMP 或按TESTING步骤将临时文件放本项目work内。真实tensor测试在没有PyTorch时显示skipped；不能将skipped说成通过。

## 7. RunningHub 中国站：待确认，不冒充已部署

已有证据与待确认条件见 `docs/RUNNINGHUB.md`。
1. 请求 RH 确认能否收录/为你的工作台安装该ZIP、自定义前端是否加载、Python与HTTPX版本。
2. 确认每个API域名、结果CDN域名、HTTPS证书链、Authorization/API-Key头和外连政策。
3. 确认服务端环境变量/密钥存储与租户隔离。**不能改成Key节点输入来迁就云端**。
4. 确认runtime持久卷；无持久卷/多副本不共享记录不能保证跨重启去重。
5. 先云端验证导入/`object_info`/仅正式模型发现（是否免费需先确认），再在明确授权后只做一笔付费编辑，保存taskId、实际输出、日志和耗时。

RH API能提交整份工作流JSON，不意味着安装里面的Python节点。RH节点库已收录、允许私有上传、允许外连、真正执行成功是不同证据。

若RH不允许自定义节点/外连，可在自控ComfyUI执行本适配器，或由RH已收录且符合秘密管理要求的标准HTTP节点调用自控网关；仍须验证入口可达和防重试。网关不是绕过RH政策的办法，无法承诺无需已收录桥接节点。

## 8. 本轮真实接通还缺什么

请提供供应商**正式图像编辑文档/请求示例**（同步或异步、上传/结果、mask语义），真实编辑模型ID与参数/费用/能力，正式模型发现接口（如存在），RH安装/外连/秘密保存答复。Key请放服务器环境变量或私密保存界面，不要贴聊天/工作流。没有你进一步授权，本项目不会调用任何付费图像接口。

SubRouter只作第一参考，不硬编码。取证到其官方目录对应的路由差异及大陆服务限制提示；具体编辑multipart/返回/mask与模型发现仍未由真实接口验证，不能把目录名或价格当契约。

## 9. 文件/长期维护

`h3_adapter/config.py` 配置/私密Key；`protocol.py` 两类HTTP协议、上传/发现/结果；`ledger.py` 跨进程SQLite占位与预算；`engine.py` 能力筛选/主备/恢复；`nodes.py` Comfy端口；`web/` 管理界面；`tests/` 免费回归；`examples/` 独立最小图；`docs/` 来源/限制/交接。协议覆盖已声明的HTTP multipart/JSON/API-Key/Bearer/上传/GET轮询，不保证任意HMAC签名、WebSocket、gRPC或不公开协议也可只填URL；这类供应商可通过标准HTTP网关归一化，或需要明确新增协议适配。

许可证：自有源码MIT；HTTPX BSD-3-Clause；Pillow MIT-CMU（以 licenses/pillow-0-LICENSE 原文为准）。本包第三方许可见 `docs/THIRD-PARTY.md` 与 `licenses/`；发行文件哈希见 `SOURCE-MANIFEST.json`。没有复制无LICENSE候选；不开源上游代码混入包，没有新增视频/文本/复杂Gateway服务。


0.1.5 构建器仅收集 `scripts/build_release.py` 的精确发行文件白名单，新增发行文件需人工加入；`config/providers.json` 始终由默认禁用的公开 example 生成。白名单不能识别已列入文件内被人为写入的秘密；Git 忽略也不能识别任意名字的秘密文件。GitHub 发布前须审查实际暂存内容和文档中的个人绝对路径。当前变更见根目录 `CHANGELOG.md`；旧版本记录见 `docs/CHANGELOG.md`。

## GitHub 源码安装与参数示例

在 ComfyUI 根目录执行：

```sh
git clone https://github.com/GPR-DG/ComfyUI-H3-Adapter.git custom_nodes/ComfyUI-H3-Adapter
python -m pip install -r custom_nodes/ComfyUI-H3-Adapter/requirements.txt
```

首次启动前在插件目录复制 `config/providers.example.json` 为 `config/providers.json`。示例供应商默认禁用；把 `base_url`、`edit_path`、逻辑别名对应的真实 `models`、报价、Mask 能力及允许参数按供应商文档填写，再启用。密钥放服务器环境变量（`key_env`）或本节点管理界面的私密存储，不能放进工作流、配置模板或 Git。

最小工作流：LoadImage 的 IMAGE → H3ImageEdit 的 image → PreviewImage 或 SaveImage。设置 `provider=auto`、`model_alias=background-edit`、`parameters={}`；如模型允许 size，可填 `{"size":"1024x1024"}`。有 Mask 时连接同尺寸 MASK。编辑完成后查看 `status_report` 中的真实 provider/model/status。更换供应商、模型或别名后检查并重新填写参数；已经完成的同输入/nonce 请求仍读旧结果，明确需要新一笔编辑时才改变 `request_nonce`。

模型发现只提供模型 ID，不证明报价、尺寸或 Mask 能力。API 协议映射与配置例子见 `docs/PROTOCOLS.md` 和 `config/protocol-variants.example.json`；模型 ID、价格和能力需由维护者按正式文档确认。RH 接入前必须确认自定义节点安装、外连、秘密管理和持久化条件。

## H3K 缺失节点交付（0.1.8）

八类 H3K 已纳入 `h3_kontext_bridge` 并由根入口注册；不要同时安装旧独立 H3K 包。安装精确 Core feature commit，不改现有 H3 API 功能与 H3 底座。逐节点审核、复现修复、性能对比、真实 ComfyUI 免费执行器验证及未验证边界见 [H3K-DELIVERY](docs/H3K-DELIVERY.md)。
