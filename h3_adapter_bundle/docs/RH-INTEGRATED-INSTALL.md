# RH 技术人员安装说明：API + A2 BackgroundBridge 单仓库

本仓库版本 0.1.7 同时提供 `H3ImageEdit` 和七个 `H3A2*` Bridge 节点。API 与 Bridge 只安装一个目录 `ComfyUI/custom_nodes/ComfyUI-H3-Adapter`，不再单独安装 `ComfyUI-H3-A2-BackgroundBridge`。现有旧 Bridge 安装应由管理员移出 custom_nodes 后重启，避免同名节点覆盖；不要同时保留两个副本。

## 1. 安装位置和依赖

在 RH 实际运行任务的 ComfyUI 容器/环境中安装。只有上传工作流 JSON 并不能安装 Python 插件。请先确认该环境允许安装第三方节点、使用本插件 JS 扩展和管理路由、配置服务器环境变量与持久存储，以及访问实际供应商的外部 HTTPS 服务。当前交付没有执行 RH 云端任务，这些权限需 RH 技术人员实测。

普通 Linux 环境示例，`COMFY_PYTHON` 必须改为该 ComfyUI 实际使用的 Python：

```bash
cd /path/to/ComfyUI
export COMFY_PYTHON=/path/to/comfy-venv/bin/python
git clone https://github.com/GPR-DG/ComfyUI-H3-Adapter.git custom_nodes/ComfyUI-H3-Adapter
"$COMFY_PYTHON" -m pip install -r custom_nodes/ComfyUI-H3-Adapter/requirements.txt
cd custom_nodes/ComfyUI-H3-Adapter
test -e config/providers.json || cp config/providers.example.json config/providers.json
git rev-parse HEAD
```

已有本仓库则在维护窗口中记录当前 SHA，执行 `git pull --ff-only`，安装新的 requirements，再重启。交付报告提供本次推送的精确 commit SHA；需要锁定版本时执行 `git checkout <交付报告中的新 SHA>`。不要对已有私人配置执行覆盖复制或 git reset。

Windows portable 从 ComfyUI portable 根目录执行：

```powershell
git clone https://github.com/GPR-DG/ComfyUI-H3-Adapter.git .\ComfyUI\custom_nodes\ComfyUI-H3-Adapter
.\python_embeded\python.exe -m pip install -r .\ComfyUI\custom_nodes\ComfyUI-H3-Adapter\requirements.txt
```

随后按 README 的首次初始化命令只创建缺失的 providers.json。运行依赖为 HTTPX、Pillow、NumPy；PyTorch/aiohttp 使用 ComfyUI 自带环境，不另装替换 CUDA/PyTorch。插件根目录直接包含 `__init__.py`、`nodes.py`、`h3_adapter/`、`h3_background_bridge/` 和 `web/`，不要额外嵌套一层 ZIP 目录。

本次统一 API/Bridge 安装，不替换既有 H3 正式项目、Z-Image 模型或其他工作流依赖。背景运行仍需原 H3 Background Core 提供 `H3CBackgroundResolve` 等 Core 节点及其 background-reference-nodes 接口（候选原先要求 feature/background-reference-nodes，e1516896）。Core 可在既有 H3 插件中提供；Bridge 导入时不要求 Core 已加载，执行时通过注册表找 Core。原工作流的 H3 runner、EasyUse、Qwen、Z-Image、视频/裁剪等插件与模型依赖同样须已有。完整节点类型清单见 `docs/INTEGRATED-WORKFLOW-NODES.json`。仅八个新增节点加载成功不代表全部 121 节点的模型依赖已就绪。

## 2. 重启后验收八个注册名和管理入口

访问实际 ComfyUI 服务的 `/object_info`，必须同时出现：

- `H3ImageEdit`
- `H3A2Recipe`
- `H3A2BackgroundResolve`
- `H3A2BackgroundWashClaim`
- `H3A2APISource`
- `H3A2APIGuard`
- `H3A2PromptCapture`
- `H3A2BackgroundFinish`

API 节点位于 `H3/API`，Bridge 位于 `H3/A2 Background`。浏览器应加载 `WEB_DIRECTORY=./web` 的 `h3_adapter.js`。在 H3ImageEdit 节点分别确认 **H3 供应商 / 密钥** 和 **H3 搜索 / 选择模型** 两个按钮。供应商界面应能设置 Base URL、主备供应商、模型别名及 Key；模型搜索应从所选供应商读取目录并映射模型，不能把目录返回成功当作该模型编辑协议已验证。

管理路由包括 `/h3-adapter/config`、`/h3-adapter/key`、`/h3-adapter/models`。远端/反向代理访问管理界面需要服务端 `H3_ADAPTER_MANAGEMENT_TOKEN`，通过 RH 的服务器秘密管理设置；前端按提示输入管理令牌。服务端 `H3_ADAPTER_DISABLE_MANAGEMENT=1` 会禁止这些操作。不要为云端部署取消既有管理鉴权。若 RH 不加载自定义前端或拦截管理路由，应明确报告两个按钮无法在该平台使用，不能以本地测试通过替代该项验收。

Key 只保存在服务器 `secrets.private.json` 或供应商指定的环境变量，不填进工作流 JSON。`H3_ADAPTER_CONFIG` 可以指定租户私有配置路径，密钥文件在其同级；`H3_ADAPTER_RUNTIME` 指定私有持久账本/结果目录。确保工作进程可读写并在重启/重新排队后持久保存；避免共享不同租户的密钥、管理令牌或请求账本。默认示例供应商全禁用，实际 Key/模型/地址由管理员配置。

## 3. 工作流和哈希验收

导入 `workflows/H3_A2_API_ZImage_BackgroundCache_INTEGRATED.json`。与二次取证候选相比，121 个 nodes 和 251 条 links 对象完全相同；只增加 `extra.integrated_repository` 元数据，历史审计字段仍保留。七个 Bridge 注册名及接口未改，因此无需调整节点/端口/连线。用户先选择自己的视频/图像输入和已安装模型，不要复用历史临时输入路径。

`h3_background_bridge/adapter-required-sha256.json` 固定六个实际集成适配器文件的 SHA256。用 ComfyUI 的 Python 在插件根运行：

```bash
"$COMFY_PYTHON" -c 'import json,hashlib,pathlib; r=pathlib.Path("."); p=json.loads((r/"h3_background_bridge/adapter-required-sha256.json").read_text()); assert all(hashlib.sha256((r/n).read_bytes()).hexdigest()==h for n,h in p.items()); print("adapter pins OK")'
```

`.gitattributes` 将校验源文件固定为 LF，避免 Windows/Linux 换行转换导致失配。运行 Recipe 时仍逐个验证源码；发生 `source differs from the audited candidate` 应恢复交付的完整 commit，或重新审计并生成匹配的版本清单，不能删除/跳过校验。不要只覆盖适配器子目录或只升级 Bridge。

## 4. 免费验证与云端验收边界

技术人员可在本地或有终端权限的 RH 测试环境，用现有 ComfyUI 宿主执行以下免费 Mock；所有供应商为本机 HTTP，仍需允许 localhost 连接：

```bash
"$COMFY_PYTHON" -m pip install -r requirements-dev.txt
"$COMFY_PYTHON" -B -m unittest discover -s tests -v
"$COMFY_PYTHON" -B scripts/verify_comfyui.py --host /path/to/ComfyUI --work /path/to/private/test-scratch
"$COMFY_PYTHON" -B scripts/independent_http_smoke.py --source . --output /path/to/private/test-scratch/http-smoke.json
```

`verify_comfyui.py` 使用真实 ComfyUI loader，核对八节点、管理路由和 Bridge 六文件哈希，执行有/无 MASK 的本机 Mock、账本重放、宿主 Save/Preview。`test_integrated_bridge.py` 还覆盖源码篡改拒绝、配置快照/Key 变化、宽高比阻断和图数量。开发测试日志必须保存在私有 scratch，不能提交到 GitHub。

本次开发者还在隔离宿主运行 11 项真实 Core/Bridge 回归与 22 个真实 Comfy 调度场景（6 正常成功、16 预期失败/阻断），使用只读既有 Core；Qwen/Z 使用明确标记的 CPU 替身，H3 末端使用输入边界观察器。没有调用收费供应商，没有实际模型生成、完整 H3 MP4 或 RH 执行证据。背景 READY 表示流水线完成，不代表去人物或洗图质量已认证。API 宽高比不符会报错并阻断下游；只有同宽高比的分辨率变化允许缩放，禁止拉伸裁剪替代。

0.1.7 已使用受限原始压缩流与 ExecutionBlocker 修复上述本地路径。需要支持 comfy_execution.graph.ExecutionBlocker 的 ComfyUI；无该宿主 API 的库调用保留空 IMAGE 合同。队列完成可能仍显示 success，应验收 API status_report 和真实图片输出。

RH 最终应另行记录 commit SHA、八节点 object_info、两个按钮/管理路由、Core 与模型依赖、持久账本重启重放，以及针对实际供应商协议/网络的结果。没有这些平台现场记录，验收状态保持 **RH 未验证**。

## 5. 0.1.7 账号与升级部署合同

每个租户使用独立 OS 进程/权限、H3_ADAPTER_CONFIG（及同级 Key 文件）、H3_ADAPTER_RUNTIME 与管理 Token；仅分开网页会话不能隔离服务器全局 STORE。固定持久目录必须在重启后保持，不能清账本来恢复任务。出口防火墙/平台代理须限制供应商 HTTPS 目的地，配置接口是管理员权限接口，插件不验证 HTTPS 目标属于公网。

provider.account_id 可在非秘密 JSON 中设置为真实同账号的稳定标识（非空、最多128字符）；须在受理原任务前配置，同账号 Key 轮换保持该值。该值是管理员声明，不是平台账号认证。未证明账号则缓存/GET 阻断；恢复原 Key 后仍用原 nonce 恢复。不同账号不用相同 account_id，使用独立目录和进程。

保留旧账本升级时，旧 Bridge Prompt 身份变化可能导致新请求 ID。0.1.7 默认对含旧提交快照的账本阻断新 ID，错误 legacy_journal_new_request_requires_review。先用旧版本记录核对已付费任务/状态；确认确实允许新任务后由管理员设置 H3_ADAPTER_ALLOW_LEGACY_NEW_REQUESTS=1。该开关不关闭已有请求防重、凭据授权或源码校验；不要删除旧账本、伪造快照或自动重发 uncertain 请求。没有凭据指纹的历史记录需人工核对。

详细独立判定与测试替身范围见 [AUDIT-017.md](AUDIT-017.md)。
