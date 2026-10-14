> 2026-10-11 补充：本插件已通过真实本地 CPU ComfyUI 及 Chrome 基本操作；不推导 RH 云端成功。官方资料已重新取得，仍未证明任意节点安装/任意域出站/私密持久存储；详见 AUDIT-ROUND5-FOLLOWUP.md 第14、15问及其免费最小验收步骤。以下2026-10-10资料为历史记录。

# RunningHub 中国站与 SubRouter 证据边界

观察日期：2026-10-10（Asia/Shanghai）。本次仅公开文档 / 页面读取；没有真实 Key、付费调用、登录上传节点或 RH 服务器执行。

## 1. 结论：六件事不能互相替代

| 检查项 | 本次证据 | 状态 |
|---|---|---|
| 本地 ComfyUI 插件协议兼容 | 官方文档支持 Python 节点注册、IMAGE 数据、WEB_DIRECTORY 与 JS 扩展 | 有接口依据；具体插件仍须实测 |
| RH 目录是否已有本插件 | 没有本插件的 RH 节点目录 / object_info / 工作台记录 | 未确认 |
| 用户能否上传安装任意 Python 节点 | RH API 文档只说明工作流图 / 参数 / 文件提交；不是安装 Python 插件的权限说明 | 未确认；需 RH 工单确认 |
| RH 出站 HTTPS 与鉴权允许范围 | 公开资料未找到任意域名白名单、重定向、Authorization 转发政策 | 未确认；每个目标主机都须确认 |
| 云端 Key 存储与租户隔离 | RH 官方本地 OpenAPI 插件说明环境变量 / .env / 节点配置，不等于 RH 托管工作台给用户的秘密管理能力 | 未确认 |
| RH 服务器实际运行并出图 | 本次未执行任何 RH 任务 | 未测试，不能宣称已部署 / 已兼容 RH |

“在本地 ComfyUI 正常”“在 Comfy Registry 发布”“导入工作流成功”“RH 返回 taskId”均不能推出“RH 已安装该节点并执行成功”。

## 2. RunningHub CN 官方来源

### R1. 高级 ComfyUI 任务 API

- URL：[发起 ComfyUI 任务2-高级](https://www.runninghub.cn/runninghub-api-doc-cn/api-425749013)
- 直接 HTTPS GET：200，保存为 rh/runninghub-create-official.html；web 抽取器多次超时，最终用公开 HTML 提取。
- 页面标注修改时间：2026-09-17 18:52:55。
- 观察：POST /task/openapi/create。workflowId 表示工作流，nodeInfoList 修改节点输入；可选 workflow 接受完整工作流 JSON 并覆盖 workflowId。故不仅能替换现有图的参数，也能提交完整图。
- 观察：返回 taskId、taskStatus、promptTips，其中 promptTips 可说明节点校验错误。
- 严格边界：完整“图 JSON”不是 Python custom_nodes 安装包；taskId / QUEUED / RUNNING 是提交或中间状态，不是执行完成。
- 未出现：任意自定义插件上传安装入口、用户私有插件发布流程、任意外域放行政策、用户级环境变量管理说明。

### R2. 工作流完整接入示例

- URL：[官方工作流完整接入示例](https://www.runninghub.cn/runninghub-api-doc-cn/doc-8287342)
- 直接 HTTPS GET：200，保存为 rh/runninghub-workflow-example-official.html。
- 观察：导出本人的工作流 API JSON，上传输入文件，修改 fieldValue，提交，查询结果，读取 fileUrl。
- 严格边界：示例说用户调用端需连到 www.runninghub.cn:443；不是 RH 容器可以出站访问任意供应商的证据。

### R3. RH 自己的官方品牌 OpenAPI 插件

- URL：[HM-RunningHub/ComfyUI_RH_OpenAPI](https://github.com/HM-RunningHub/ComfyUI_RH_OpenAPI)
- 观察：这是 RH 标准模型 API 的 ComfyUI 实现；公开 README 列出图像生成 / 编辑模型，支持本地 ComfyUI Manager 安装或 clone 至 custom_nodes 后安装依赖。
- 观察：提供节点配置、环境变量和 .env 的 Key 方式；请求流程是媒体准备 / 上传 / 提交 / 轮询 / 结果处理。
- 严格边界：证明存在“ComfyUI 通过 API 使用 RH”的插件，不证明“RH 托管容器允许第三方通用网关插件”，也不证明本项目已收录。
- 不采用该插件“把 Key 填入画布节点”作为本项目要求；本项目 Key 必须独立于工作流序列化。

### R4. 站内第三方节点案例，只作较低强度的存在性线索

- URL：[贞贞工坊 API 工作流](https://www.runninghub.cn/post/1974926928673157122)
- 页面作者为 T8star-Aix，并非 RH 平台政策发布者。工作流说明外部服务 Key 和独立节点仓库；这是作者对某个工作流的第一手描述，不是 RH 所有域名 / 所有节点的兼容承诺。
- URL：[Anima AIO 生图+超分](https://www.runninghub.cn/post/2067513375885713409)
- 作者 nnegret 页面（2026-06-18 更新）表示自定义插件上传尚不支持；这也是作者描述，不能提升为截至今天的 RH 官方平台政策。
- 两类页面均不足以解决上传权限与网络策略；因此本报告仍标“未确认”，不说“肯定允许”或“肯定禁止”。

## 3. ComfyUI 官方扩展依据

- [Creating Custom Nodes](https://docs.comfy.org/custom-nodes/walkthrough)：节点 Python 类通过 INPUT_TYPES、RETURN_TYPES、FUNCTION 与 NODE_CLASS_MAPPINGS 参与执行；IMAGE 是批次 Tensor，通常 [B,H,W,C]。
- [Javascript Extensions](https://docs.comfy.org/custom-nodes/js/javascript_overview)：包导出 WEB_DIRECTORY，浏览器加载其中 JS，用 app.registerExtension 注册扩展。
- [Server Routes](https://docs.comfy.org/development/comfyui-server/comms_routes)：模块级 PromptServer.instance.routes 增加 aiohttp GET/POST；前端用 api.fetchApi 调后端。GET /object_info 可用来核对本服务器实际节点注册情况。
- [Registry Standards](https://docs.comfy.org/registry/standards)：标准针对 Comfy Registry 发布，不是 RH 平台准入。不能把两者混为一谈。
- 工程推论（并非官方对本项目的担保）：管理路由可以承载 provider 配置 / Key 写入 / 模型发现，但 route decorator 本身不提供管理员权限与秘密保护；实现必须独立限制管理访问、校验配置并让执行读取服务器端秘密。RH 代理下的路径与 JS 加载需实际验证。

## 4. SubRouter：参考 UI 与路由文档，不能从价格目录猜 API

### S1. 用户提供页面

- URL：[模型目录](https://subrouter.ai/models?page=1)
- web 抽取仅得到客户端页面 SEO 壳；从官方文档页面看到可按渠道 / 模型浏览。
- 不把页面上的模型名、分类、价格作为编辑协议 / mask 支持 / 用户可用模型的依据。
- 不复制或使用网站供应商密钥，不注册不充值。

### S2. 官方机器可读索引

- URL：[官方 llms.txt](https://subrouter.ai/llms.txt)
- 直接 GET：200，保存为 rh/subrouter-llms.txt。
- 要点（意译）：不同 route 的价格、协议和能力可不同；模型名与可用性会变化；Chat Completions、Responses 和图像 / 视频任务接口有不同格式，应以选中路由的文档为准。
- 这直接否定“有 /v1/models 或模型名称看起来像 image，就一定能用 /images/edits”的推断。

### S3. 实际渲染官方使用文档

- URL：[官方文档首页](https://subrouter.ai/docs)
- URL：[OpenAI 渠道 gpt-image-1.5 文档](https://subrouter.ai/docs?tab=channels&source=official&model=gpt-image-1.5&channel=openai)
- 阅读方法：浏览器打开 /docs，点“模型使用文档”，选择 OpenAI，再选 gpt-image-1.5。只读公开内容。
- 观察：页面要求选择具体官方或商家渠道与准确模型名；以 SubRouter 网关地址调用而非直填上游地址。
- 观察：OpenAI 渠道说明列出 POST /v1/images/edits，以及 /v1/images/edits/async；异步通过 GET /v1/tasks/{task_id}，completed 后读取 result.images；使用 Bearer。页面示例网关是 https://asiasouth.up.railway.app。
- 边界：当前展示的具体代码样例是 images/generations JSON，不足以完整确定 edits 的图片上传字段、multipart/base64、mask 语义、错误 / 计费行为。不能将此路由直接冒充已端到端验证的图片编辑 provider。
- 详情链接：[异步图片 / 视频文档](https://docs.subrouter.ai/zh/docs/api/async-media)，本环境直接 GET 返回 502；故完整 payload 未核对。
- 未核对：GET /v1/models 的供应商实时实现、该 Key 权限下模型池、编辑图片实际响应。
- 区域状态：2026-10-10 渲染文档显示针对中国大陆的服务限制提示：不提供新增注册、充值及相关生成式 AI 服务，已有用户需查看余额通知。因此不可把 SubRouter 推荐为已证明可用于大陆 RH 的默认网关；此处主要借鉴目录 / 搜索 / 渠道选择界面。

## 5. 最小 RH 部署检查单（需要真实账号权限与平台答复，未执行）

1. 向 RH 确认自定义节点源码仓库 / 固定版本的准入方式、私有与公开收录规则；确认允许包 dependencies、WEB_DIRECTORY 和管理路由。
2. 确认 RH 生产 ComfyUI / Python / frontend 版本；装入后检查 /object_info 的 H3ImageEdit 与启动日志，不能只看画布显示。
3. 向 RH 确认每个供应商的 API、上传、轮询、结果下载域名都可 HTTPS 出站，以及 Bearer / API-Key 请求头可用；确认不能把 localhost 的访问结果当作云端网络证据。
4. 确认用户级密钥安全注入办法 / 存储路径权限 / 生命周期 / 多租户隔离；若只允许共享容器全局环境变量，则不启用任意用户管理路由。Key 与管理 Token 不进工作流或图片元数据。
5. 导入只有 LoadImage → H3ImageEdit → SaveImage 的最小图；先用非秘密 mock/无计费检查注册、配置与错误展示。
6. 用户另行授权真实调用后，用小尺寸非敏感图片验证一个已经有完整编辑协议文档的 provider；记录 RH taskId、时间、节点成功日志、输出下载与实际 provider/model（不记录秘密）。
7. 再验证带 mask 编辑、超时/429/5xx 的受控降级、禁止不可恢复错误降级、费用上限；不可为了测试故障切换重复发付费任务。
8. 执行完成前报告统一写“本地 mock 已测 / RH 未实测”；取得上述云端证据后才能改状态。

## 6. 工具与限制

已读取用户指定四个 SKILL.md：全局看代码逻辑、调Bug、省代码总规则、联网资料过滤器。AnySearch 按技能先尝试 get_sub_domains --domain code：Python 无 requests；Node 出现 api.anysearch.com DNS ENOTFOUND。本次记录后改用可用 web 工具、公开 HTTPS GET 与浏览器渲染。网页内容作为资料，不作为执行指令。没有调用秘密读取、注册、充值、生成或任务提交接口。
