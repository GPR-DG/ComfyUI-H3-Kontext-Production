# 2026-10-12 开发测试候选：当前验证

以下当前摘要优先于后面的历史记录。Python discovered=174，run=171，pass=171，failure/error/skip=0；按既有约束排除报告列出的 3 项 Git 写入夹具。原断言未改，新增授权回归用生产 aiohttp 路由验证无效/正确 token。

运行 6 套前端检查：

```powershell
$files = @('test_frontend.mjs', 'test_frontend_review.mjs', 'test_round3_frontend.mjs', 'test_round4_frontend.mjs', 'test_final_frontend.mjs', 'test_development_frontend.mjs')
foreach ($name in $files) {
    node "tests/$name"
    if ($LASTEXITCODE -ne 0) { throw "Failed: $name" }
}
```

新授权回归可在插件根执行 `python -B -m unittest discover -s tests -p test_development_upload.py -v`。全套 Python 的本轮外部 runner 在 discover 后逐项排除 Git 写入夹具；直接运行后面的历史全套命令会执行这些夹具，结果范围不等同于本轮。所有合成凭据不可用于真实收费服务。

当前独立验证包括 27 类真实 loopback TCP Mock、生产路由/实际 Chromium 的 9 组管理探针、Windows 只读替换失败后临时清理和无新 POST 恢复。实际官方 ComfyUI CPU 宿主中导入、路由、IMAGE/MASK、成功缓存与 SaveImage/PreviewImage 消费通过。五类无图状态仍触发实际 PromptExecutor 的消费者 IndexError，不能把宿主探针进程退出 0 解释为全部工作流通过。HTTP gzip/deflate/多重编码在 64 KiB cap 之前先生成 4 MiB 块；没有生产 OOM 证明。

外部独立探针与含本机路径的原始日志留在本地交付，不随源码公开。真实供应商、账单、RH、目标文件系统和跨版本兼容未验收。Stable Release：NO，详见根目录 FINAL_AUDIT_REPORT.md。

---

# 以下为历史测试记录（不是本次源码认证）

> 2026-10-11 本次最终独立验证以根目录 FINAL_AUDIT_REPORT.md 为准；下方旧计数为历史记录。当前 173 项 Python（无 skip）、5 套 JS、27 类 TCP Mock、官方 ComfyUI CPU 宿主均纳入验收。未调用付费接口，未验证 RH。一次 Windows WinError 5 失败保留为部署存储风险，成功重跑不消除该记录。

> 0.1.5 当前验收：真实 Torch 与实际 CPU ComfyUI 宿主、Chrome 管理界面已通过免费 Mock。以下旧版本计数/skip 是历史记录；最新详细范围见 AUDIT-ROUND5-FOLLOWUP.md，最终源码/ZIP 全套结果在交付证据 test-summary.json。新独立 HTTP 冒烟：在插件根运行 `python scripts/independent_http_smoke.py --source . --output ../work/independent-http.json`；其27类场景使用假Key和真实本机TCP，不读取商家Key。相同源/ZIP须分别执行。

> 当前版本 0.1.4。第五轮独立审计见 AUDIT-ROUND5.md；最终源码全套 154 项：153 pass、1 真实 Torch skip。此前完整回归和重复检查仍复现 Windows os.replace 的 WinError 5，根因及目标存储稳定性 UNVERIFIED，不能用通过重跑覆盖失败证据。包内结果以第五轮报告与 audit-round5/package-verification.json 为准。下文旧计数保留为历史。

> 历史说明：本文原验证计数/审查对应 0.1.0；当前 0.1.1 结论和独立发行包回归见 AUDIT-ROUND2.md，不能将旧计数视为现版验收。

> 最终更新：全套已增加到70项，69通过、1真实Torch跳过；下文60项/59通过为早期验证快照。以VALIDATION.md最终记录为准。

# 免费本地测试与验收记录

## 本轮实际结果（2026-10-10 03:10，Asia/Shanghai）

- Python：`python -B -m unittest discover -s tests -v`，**共 60 项，59 通过，1 skipped，0 失败/错误**；退出码 0。
- Engine：其中 **25 项**使用真实 `ThreadingHTTPServer` + HTTPX + 临时 SQLite/结果文件；不是仅 MockTransport 单测。
- 前端：`node tests/test_frontend.mjs` 退出码 0，验证扩展 hooks、非序列化操作控件、密钥弹窗、模型映射、报告和管理员令牌重试。它是前端合同测试，不是完整 ComfyUI 浏览器实测。
- 模拟 CLI：`python -B scripts/mock_server.py --port 0 --duration 0.05 --async` 退出码 0，服务器仅绑定 `127.0.0.1`，完成后已关闭。
- 交付配置闭环：实际读取 `config/providers.mock.json`，本机 8788 模拟服务主 p0 返回 401，p1 返回已知 PNG；输出 `success / p1 / estimated_cost=0.0`。同输入同 nonce 再开 Engine 后 `cached=true`，POST 序列仍仅 `[p0,p1]`，没有第二次提交。
- 初始主备测试在 Engine 未实现时确实 RED；实现后 GREEN。扩充测试的第一次失败包含无效改路由夹具、过短总连接预算、预算拒绝状态名称差异；均按真实契约修正测试，而非隐瞒生产错误。

**唯一 skipped：** `test_real_torch_image_output_has_standard_bhwc_shape`，原因是真实 PyTorch 不在隔离测试环境。两次 CPU PyTorch 安装尝试均受磁盘空间阻塞，残留只在项目隔离环境内清理。NumPy 端口替身/PNG MASK 测试通过，不能替代真实 tensor、完整 ComfyUI 进程或 RH 实机证据。没有调用 SubRouter、RH 或任何收费图像服务；没有测试 AI 真人移除/背景修复效果。

## 关键行为断言

| 范围 | 实际断言 |
|---|---|
| 主 + 3 备 | 401 明确拒绝后按配置顺序 p0→p1→p2→p3；每路 POST 一次，备用采用其真实模型映射 |
| 安全前提 | 单家连接预算 .1 秒、总预算 1 秒，连接前拒绝可换家；读超时/HTTP500/受理后缺图绝不向备用再付费 |
| 持久去重 | 同输入/nonce、Engine 重建仍读取磁盘缓存；明确改变 nonce 才新 POST；同 nonce 双线程争用仅一个 POST |
| 异步恢复 | HTTP202 + task_id 后只 GET 同任务；达到轮询上限为 awaiting_result；即便更换 primary/禁用原家仍用受理快照恢复；终态失败不另开备用任务 |
| 模型能力 | 不支持 MASK、多图容量不足、参数未允许、禁用供应商或缺 Key 时先筛选，不静默丢 MASK；备用请求保留 mask/model/参数 |
| 费用 | 单请求上限排除超价/未知价；累计估计预算跨 nonce/Engine 持久；明确拒绝释放预留，未决/异步占用仍保留；拒绝结果可为 no_provider 或 blocked，但没有新 POST |
| 固定路线/冷却 | 手动指定家或关闭自动切换均不切换；安全拒绝后的冷却在新 Engine/nonce 下仍生效 |
| 协议/管理 | JSON/multipart/上传/GET发现、响应大小/gzip、TLS/结果主机与认证边界、有限尝试、密钥不回显、反向代理与跨域管理拒绝均有回归 |
| PNG/MASK | mock 只是确定性 2×2 蓝色 RGBA PNG；白色 MASK 编成透明 edit alpha，声明灰度模式时按模型转换 |

## 复现全部测试

以下 PowerShell 从插件目录执行；将 `$python` 改为实际 Python（推荐 ComfyUI 自己的 Python）。独立开发环境需 HTTPX、Pillow、aiohttp、NumPy；可安装 `requirements-dev.txt` 和 `numpy`。不需要为了这套免费测试另外安装 GPU 框架；没有 Torch 时对应真实 tensor 项会明确 skipped。

```powershell
$package = (Get-Location).Path # 从插件根目录执行
Set-Location -LiteralPath $package
$python = 'python' # 或 ComfyUI 自己的 Python 可执行文件
New-Item -ItemType Directory -Path '..\work\tmp' -Force | Out-Null
$env:TEMP = (Resolve-Path '..\work\tmp').Path
$env:TMP = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
# 新建独立环境才需要：& $python -m pip install -r requirements-dev.txt numpy
& $python -B -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Python tests failed' }
node tests/test_frontend.mjs
if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed' }
node tests/test_frontend_review.mjs
if ($LASTEXITCODE -ne 0) { throw 'Frontend review tests failed' }
node tests/test_round3_frontend.mjs
if ($LASTEXITCODE -ne 0) { throw 'Round3 frontend tests failed' }
node tests/test_round4_frontend.mjs
if ($LASTEXITCODE -ne 0) { throw 'Round4 frontend tests failed' }
node tests/test_final_frontend.mjs
if ($LASTEXITCODE -ne 0) { throw 'Final frontend tests failed' }
```

测试临时目录在插件父目录的 `work/tmp`；Engine 自己的回归夹具也显式使用该目录。被测密钥为进程内假值，mock 不转发请求，不连接真实提供商。端口 0 表示系统选择空闲本机端口，避免依赖固定公网地址。

## 免费模拟演示

### 1. 启动服务（终端 A）

```powershell
Set-Location -LiteralPath 'C:\path\h3-adapter\ComfyUI-H3-Adapter'
python -B scripts/mock_server.py --port 8788
```

服务只监听 `127.0.0.1:8788`。默认 p0=401、p1/p2/p3=成功，返回已知蓝色 PNG，不具有语义编辑能力。`--primary-status 500` 可观察不明状态禁止切换。Ctrl+C 关闭服务。`--port 0 --duration 0.05` 可做短时 CLI 冒烟；交付 mock 配置固定 8788，因此不能拿随机端口直接套该配置。

### 2. 纯 Python 免费闭环（终端 B，无 Torch/ComfyUI）

```powershell
Set-Location -LiteralPath 'C:\path\h3-adapter\ComfyUI-H3-Adapter'
$env:H3_MOCK_KEY = 'mock-only-not-a-real-key'
@'
import json
from pathlib import Path
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
engine = Engine(ConfigStore(Path('config/providers.mock.json')), Path('../work/mock-demo-runtime'))
image = Path('examples/example_input.png').read_bytes()
result = engine.edit([image], prompt='free fixture check', max_cost=0, request_nonce=0)
print(json.dumps(result['report'], ensure_ascii=False, indent=2))
if result['report']['status'] == 'success':
    Path('../work/mock-demo-output.png').write_bytes(result['images'][0])
'@ | python -B -
```

首次应为 `success`、`provider=p1`、费用估计 0；再次完全同输入/nonce 从持久缓存返回，`cached=true`。输出在项目 `work/mock-demo-output.png`，只是测试夹具。需要新的**免费 mock**调用才改 nonce；真实提供商改 nonce 意味着可能再次付费。runtime 不能用于多个互不信任租户共享。

### 3. ComfyUI 画布演示（待真实环境执行，不属于本轮通过结果）

在启动 ComfyUI 的服务器终端设置 `H3_MOCK_KEY`，以及 `H3_ADAPTER_CONFIG` 为安装目录内 `config/providers.mock.json` 的绝对路径，再启动/重启 ComfyUI。mock 与 ComfyUI 必须在同一台主机；云端 127.0.0.1 不指向你的电脑。

导入 `examples/image_edit_minimal.json`，LoadImage 上传 `examples/example_input.png`，先不接 MASK；节点模型别名 `background-edit`、provider=auto。预期输出已知蓝色夹具与 p1 success 报告；验证时记录节点注册、实际 tensor、保存图片和日志。该步骤尚未在完整 ComfyUI/RH 实机执行，不能写为已完成。

### 4. 异步模拟（使用独立测试，不误用同步配置）

`--async` 会让备用服务返回已完成的 task_id；需要在对应供应商配置声明 task_id/poll_path/status/success/failure。现有 `providers.mock.json` 是同步配置，不得直接加 --async 运行画布后声称成功。已通过的免费异步恢复证据来自 `test_accepted_async_task_recovers_only_by_get_on_saved_provider` 和终态/预算回归，它们明确配置异步合同。

## 未覆盖、禁止外推

真实提供商的 multipart/MASK/模型发现合同、实际价格与计费、真人移除质量、完整 ComfyUI 画布/张量执行、RH 安装与节点收录、云端外连和租户持久卷仍待确认。当前线程并发测试不等同于跨服务器分布式幂等；只声称所测同 runtime 内持久占位。费用是用户配置的估计，不是账单硬上限。新测试/评审修复后应重新运行全套并更新此结果快照。

## 当前独立 TCP 与官方宿主验证

先安装 requirements-dev.txt，并准备插件父目录的 work/tmp（旧回归夹具使用该目录）。Python 3.10+；真实 IMAGE 测试和下面宿主脚本需要可用的 PyTorch 与 ComfyUI 依赖。

```sh
python scripts/independent_http_smoke.py --source . --output ../work/independent-http.json
python scripts/verify_comfyui.py --host /path/to/ComfyUI --work ../work/host-verification
python scripts/build_release.py --source . --output ../releases
```

verify_comfyui.py 用已有官方宿主源码的 load_custom_node 导入本插件；不开启公网服务。资产功能关闭，user/temp/output 全部写在 --work 中。当前验证宿主 SHA 见最终报告；不同宿主版本的初始化 API 可能需要单独适配验证脚本。本脚本不是生产运行的依赖。

新增 test_final_identity.py 覆盖旧配置与新 Key 错配、发现竞态、环境 Key 的删除重建恢复、同身份正常轮换、冷却身份和旧 health 表迁移。test_final_frontend.mjs 直接运行生产前端回调，验证切换清空 parameters、选择不变保留参数。旧测试未修改。
