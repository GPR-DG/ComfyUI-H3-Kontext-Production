# 协议配置手册（第一阶段：图像编辑）

## 先确认范围

本包实现了通用 HTTP 协议映射，不宣称任何尚未接入的供应商已经可用。

- `config/providers.example.json`：一个主服务商 + 三个备用服务商，**全部 disabled**，域名是 `.example.invalid`，模型 ID 必须填写。
- `config/protocol-variants.example.json`：四种请求形态的**占位模板**，不是四个已验证商业 API。实际代码只有两个 `protocol` 值：`openai_images` 和 `json_template`。
- 四种形态为：multipart 编辑、JSON 内联图片、JSON 异步任务、上传后 JSON 引用。它们可以按任意顺序分配给主/备服务商。
- 本轮只有不收费的本地 HTTP 模拟及协议回归测试；没有真实 Key、没有付费调用。**SubRouter 正式接口/模型/报价与 RunningHub 实机运行均未验证。** 2026-10-11 已独立验证真实 CPU PyTorch 和官方 ComfyUI 宿主的 Mock 闭环，见根目录 FINAL_AUDIT_REPORT.md。

接入一家真实供应商前，必须以其当前正式文档确认：Base URL、编辑路径、认证头、模型真实 ID、请求字段、结果字段、MASK/多图能力、异步查询及费用。不要仅因域名或模型名看起来像 OpenAI 就填入 `/images/edits`。

## 公共字段

| 字段 | 行为 |
|---|---|
| `id` | 配置中的服务商引用，不是密钥。 |
| `enabled` | 样例默认 false；补完并验证配置后再启用。 |
| `base_url` | 必须包含供应商要求的完整根路径（如 `/v1`）；不自动添加 `/v1`。 |
| `edit_path` | 必填、以 `/` 开头的相对路径，追加到 Base URL 后；不是替换其根路径。 |
| `auth.header` / `auth.prefix` | 默认 `Authorization` / `Bearer `；只声明认证格式，不在共享 JSON 中写真实 Key。 |
| `key_env` | 从该环境变量读取 Key；管理器存储的 Key 也只留在服务端私密文件。工作流不保存 Key。 |
| `timeout_seconds` | 每家请求上限，受工作流/全局剩余时间限制。上传图片、上传 MASK 与编辑提交共享剩余时限。 |
| `max_response_bytes` | 每家可选，默认 `67108864`（64 MiB）；HTTP 响应流和解码后的图片都有限额，超限停止读取。 |
| `safe_reject_statuses` | 默认 `[401,403,404]`。只有有文档依据的 4xx“未接受请求”才能添加；5xx 永远不能配置为安全回退。 |
| `models` | 逻辑别名 → 每家的真实模型 ID 与手工声明能力；同一别名可映射不同 ID。 |

例：`base_url=https://provider.example/v1` 与 `edit_path=/images/edits` 的实际请求是 `https://provider.example/v1/images/edits`。不要把 Base URL 写成完整编辑地址再重复加路径。

所有正常上游与结果下载要求 HTTPS，TLS 校验始终开启。`allow_insecure_localhost=true` 仅允许 `localhost`、`127.0.0.1`、`::1` 的 HTTP 本地模拟，不允许公网 HTTP。

### 模型能力与费用

```json
{
  "models": {
    "background-edit": {
      "id": "FILL_ACTUAL_IMAGE_EDIT_MODEL_ID",
      "task": "image_edit",
      "supports_mask": false,
      "max_images": 1,
      "mask_encoding": "alpha_transparent_edit",
      "price_upper_bound": null,
      "defaults": {},
      "allowed_params": []
    }
  }
}
```

- 先确认厂商支持 MASK 再设 `supports_mask=true`；不支持的模型不会偷偷丢弃 MASK。
- `max_images` 是明确声明的能力；上传引用方式当前仅支持一张输入图。
- `mask_encoding` 支持 `alpha_transparent_edit`（PNG 透明区编辑）或 `grayscale_white_edit`（白色灰度区编辑），按厂商文档选择。ComfyUI 的白色 MASK 表示待编辑区。
- 工作流传入的参数必须在该模型 `allowed_params` 中；`defaults` 是已确认的厂商默认请求字段。不要把不支持的参数伪装成默认值。
- `price_upper_bound` 是用户配置的保守估计，不是实时账单。存在有限额时，未知价格不会提交；不承诺控制厂商最终账单。

## 0.1.4 本地 multipart 字段合同

实际使用的 `request.image_field`、有 MASK 时的 `request.mask_field`、引用上传时的 `upload.field` 必须是非空字符串，且不包含 ASCII 控制字符或 DEL；允许 `image[]` 等正常字段名。非法值报告 `invalid_multipart_field`，对应主家没有 POST，释放预留、不冷却该家，自动路线可尝试合法备用。发送后的超时/断连仍遵守 uncertain/accepted 不重提规则。

## 1. OpenAI 形态 multipart 编辑

```json
{
  "protocol": "openai_images",
  "edit_path": "/images/edits",
  "request": {"image_field": "image", "mask_field": "mask"},
  "result": {
    "b64_path": "data.0.b64_json",
    "url_path": "data.0.url",
    "download_hosts": [],
    "download_auth": false
  }
}
```

这是协议片段，不是可直接启用的完整配置。请求为 multipart：`model`、`prompt`、允许的参数、PNG 输入与可选 MASK。若正式多图接口要求重复 `image[]` 字段，可把 `image_field` 改为 `image[]` 并声明相应 `max_images`；不自动猜测厂商字段名。

## 2. JSON 内联图片

```json
{
  "protocol": "json_template",
  "edit_path": "/FILL_DOCUMENTED_EDIT_PATH",
  "request": {
    "body": {
      "model": "{model}",
      "prompt": "{prompt}",
      "images": "{images_data_urls}",
      "parameters": "{params}"
    }
  },
  "result": {
    "b64_path": "FILL_RESULT_B64_PATH",
    "url_path": "FILL_RESULT_URL_PATH",
    "download_hosts": [],
    "download_auth": false
  }
}
```

模板只替换**整项字符串**。`"{params}"` 会成为 JSON 对象，`"{images_data_urls}"` 会成为数组，不会成为双重编码的 JSON 字符串。`"prefix {prompt}"` 不做局部插值，仍是字面值。

| 精确占位符 | 值 |
|---|---|
| `{model}` | 每家真实模型 ID。 |
| `{prompt}` | 工作流提示词。 |
| `{params}` | 允许的最终参数对象。 |
| `{images_data_urls}` | 所有输入 PNG 的 data URL 数组。 |
| `{image_data_url}` / `{image_base64}` | 第一张输入 PNG 的 data URL / 纯 base64。 |
| `{mask_data_url}` / `{mask_base64}` | MASK 的 data URL / 纯 base64；没有 MASK 时为 JSON null。 |
| `{image_ref}` / `{mask_ref}` | 上传接口返回的引用；需要 `upload` 配置。 |

JSON 嵌套对象和数组同样可使用这些精确占位符。它们不执行 Python、脚本或任意表达式。

### 0.1.4 固定文本字段与报告提示

固定模型和固定提示词是合法模板，不强制包含 `{model}` / `{prompt}`。例如 body 中的 `model: fixed-model-B` 将照原样发送，即使当前配置映射模型为 A。`report.model` 和节点 provider_model 中的 model 表示配置映射，不表示已解析并核实供应商实际使用的模型。

缺少完整值 `{model}` / `{prompt}` 时，报告 warnings 分别增加 `json_template_unmapped_model` / `json_template_unmapped_prompt`；有效参数（defaults 与工作流参数合并）非空却无 `{params}` 时增加 `json_template_unmapped_parameters`。提示说明没有通过标准占位符传递输入，不证明供应商实际忽略了其他自定义字段。嵌套对象/数组中的完整值占位符同样被识别；字符串片段仍是字面值。警告不改变 HTTP 请求，缓存及异步恢复保留它们，成功备用不会继承主家警告。想让界面输入直接跟随请求时使用第 2 节模板。

### 0.1.2 请求前输入映射校验

声明 `supports_mask=true` 是能力声明，不是模板自动加字段。JSON 模板仅替换 dict 的值/list 中的**完整字符串**占位符；键名、`"prefix {mask_base64}"` 片段或从 `{params}` 注入的对象不会再递归渲染。

在任何 upload/edit POST 之前：实际 IMAGE 必须映射 image/all-images 值；多图必须有 `{images_data_urls}`；实际接入 MASK 必须有 `{mask_data_url}`、`{mask_base64}` 或 `{mask_ref}`。违反时分别报告 `unmapped_images` / `template_single_image_only` / `unmapped_mask`，固定商停止，auto 可尝试合法备用，错误模板本身不发 HTTP。未接 MASK 可正常用无 MASK 模板。

引用占位符必须配置 upload；只有实际用 `{image_ref}` / `{mask_ref}` 才上传相应输入。inline 图片不因存在 upload 配置而额外上传。真正引用上传仍保持当前单图限制；不自动推断厂商字段名，也不能证明对方服务一定使用了某个字段。

## 3. JSON 异步任务

请求体仍使用第 2 节的 `json_template`，另外配置：

```json
{
  "async": {
    "task_id_path": "id",
    "poll_path": "/tasks/{task_id}",
    "status_path": "status",
    "success": ["succeeded"],
    "failure": ["failed"],
    "poll_interval": 1,
    "max_polls": 120
  }
}
```

以上只是可理解的形状示例，**不是 SubRouter 或 RunningHub 的正式路径**。必须用厂商文档替换。

- 提交返回的 task ID 存入请求记录；后续只对保存的服务商/任务 ID 发 GET 查询。
- task ID 必须是非空字符串或整数，规范化后不超过 1024 字符，不能包含控制字符或完整 API Key。
- `{task_id}` 按 URL 路径值转义；不会把供应商返回值直接拼成另一域名。
- `success` / `failure` 精确匹配供应商状态值；其他字符串状态当作 pending，受总时限和 `max_polls` 限制。
- 已接受任务的查询超时、结果下载失败或明确终态失败，都**不会新开备用任务**。相同 nonce 重跑只恢复查询/下载。

## 4. 上传后 JSON 引用

在第 2 节 JSON 请求中，把图片值换成 `{image_ref}`，并配置：

```json
{
  "upload": {"path": "/FILL_UPLOAD_PATH", "field": "file", "ref_path": "data.url"},
  "request": {
    "body": {"model": "{model}", "prompt": "{prompt}", "image": "{image_ref}", "mask": "{mask_ref}"}
  }
}
```

模板使用 `{image_ref}` 时以 multipart 上传一张 PNG，从 `ref_path` 取字符串引用；实际有 MASK 且模板使用 `{mask_ref}` 时才上传 MASK，然后提交编辑 JSON。仅配置 upload 但完全使用 inline 的模板不上传。所有步骤共享一次 submit 的剩余预算，不给每一步重新分配完整超时时间。上传接口是否计费必须向供应商确认；状态不明时采取保守停止策略。

不支持在模板内写任意多步登录、验证码、网页抓取、签名脚本或工作流编排。厂商若需要这些专有协议，应单独评估适配，不能声称配置片段已经覆盖。

## 响应、结果下载与恢复

路径使用点分隔对象键及从 0 起的数组索引，例如 `data.0.b64_json`、`result.url`。当前不支持键名中自带点号的转义语法。

- `b64_path` 优先；否则使用 `url_path`。最小实现提取明确配置的**一个结果**，并交给图像层验证，不承诺把任意数量的厂商输出全部返回。
- `download_hosts` 是小写主机名白名单，不是 URL，也不是通配符；空列表意味着禁止 URL 结果下载。API 自身主机也必须显式加入。
- `download_auth=false` 为默认。设为 true 后，也只有与 API **相同 scheme/host/effective port** 的白名单地址才带认证头；CDN 和其他端口不带 API Key。
- HTTP 重定向不跟随；不把认证转发到重定向目标。下载可能带签名 query，保留用于请求，但不写入公开日志/报告。
- 默认 64 MiB 上限约束解压后的 HTTP 响应体，也约束 base64 解码后的图片；包含 base64 的 JSON 本身同样占响应限额。gzip 只解码一次。
- SQLite 私密记录只保存必要的结果定位信息或 task ID，不保存任意上游原始响应。结果 URL 可能有敏感签名，不能公开分享数据库。
- 本地稳定 request ID 用于本安装目录的恢复，不是自动发送的厂商幂等键，也不提供跨厂商“全局一次付费”保证。

## 模型发现：辅助，不推断能力

```json
{
  "discovery": {"path": "/models", "items_path": "data", "id_path": "id"}
}
```

只 GET 显式配置路径，读取对象数组中的模型 ID 并去重。不配置（null）时不做网络发现，照常手动配置。列表出现某模型不证明它支持 image_edit、MASK、多图，也不证明价格；能力与价格仍由 `models` 明确映射。

## 回退边界与故障处理

| 情况 | 行为 |
|---|---|
| 未发送请求前的连接/连接池失败 | 在预算、能力与冷却条件允许时可换下一家。 |
| 已配置且有非接受依据的 4xx | 可安全拒绝回退；429 默认不是安全状态，只有确认语义后才能显式加入。 |
| 读/写超时、断连、不完整成功响应、响应超限、5xx | 标记 uncertain，停止新提交；不为了“保证出图”重复付费。 |
| 已接受异步任务 | 仅恢复原任务 GET 查询与结果下载。 |
| 同一输入与 nonce 已有提交/结果记录 | 使用记录，不重复 POST；欲明确新付费任务才增加 nonce。 |

HTTPX 的连接、读、写超时属于网络子阶段控制；实现还会在各子请求与响应流之间检查剩余总预算。这不是毫秒级抢占式取消保证，也不能仅凭本地超时判断远端未接受。不要删除不明状态记录后重试，除非已在供应商侧核对受理/计费情况并愿意发起新的任务。

验证命令（在安装包根目录、依赖已装好时）：

```powershell
python -m unittest discover -s tests -v
```

测试通过只证明本地协议/调度契约。商业服务商实际编辑质量、账单、RunningHub 安装权限/网络/密钥注入仍需独立验收；真实 ComfyUI 张量输出已通过本地 Mock 宿主验证。
