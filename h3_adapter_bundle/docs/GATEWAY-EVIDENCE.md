# 网关与 ComfyUI API 节点源码证据

采样日期：2026-10-10。仅核对公开仓库/官方文档，没有调用付费 API，没有使用真实密钥。完整文件快照在 `research/gateways/<owner>__<repo>/`，`metadata.json` 保存 exact SHA，`tree.json` 保存路径清单。以下行号均为该 SHA 的原始文件行号，不是网页行号。

## 结论

**当前最小可用复用栈：HTTPX + 已在 ComfyUI 中使用的 Pillow/NumPy/Torch + Python 标准库 JSON/SQLite。** HTTPX 负责 HTTP/TLS/multipart/timeouts，不重写网络库；SQLite 负责已提交、已接受、状态不明和结果缓存。只补配置映射、四家顺序调度、接受后轮询/恢复这段业务逻辑。此结论是源码比较后的工程推断，不是吞吐量基准结论。

如果用户已有 Portkey/new-api，可以把它当单一上游，但必须关闭其所有提交重试/广义回退。若确实需要几十种厂商协议和独立代理服务，再考虑 LiteLLM（非 enterprise 目录 MIT）或 Portkey（MIT）。当前四家图像编辑场景，不引入额外 Node/Go/代理数据库及其运维成本。

**关键限制：任何通用网关都无法仅凭读超时/连接重置/5xx证明远端没有接受付费请求。** 本地 request_id 不是厂商承诺的幂等键；不同服务商的幂等键也不能跨厂商去重。收到 task_id 后仅轮询该任务；读写超时或不完整响应时进入 uncertain，不能自动换厂商新提交。只在未发送请求的 ConnectError/ConnectTimeout/PoolTimeout，或有厂商明确“不接受/不计费”语义的配置4xx状态码时回退。5xx即使被配置为拒绝也始终状态不明，禁止换家提交。

## 候选比较（实际源码）

| 候选 / 固定版本 | 已核实能力 | 决策及源码证据 |
|---|---|---|
| HTTPX `b5addb64f0161ff6bfe94c124ef76f6a1fba5254`，BSD-3-Clause | multipart、同步/异步、mock transport、细分异常、TLS；底层 HTTPTransport 默认 retries=0 | 推荐作为依赖，不复制网络实现。[default.py L135–160](https://github.com/encode/httpx/blob/b5addb64f0161ff6bfe94c124ef76f6a1fba5254/httpx/_transports/default.py#L135-L160)；[exceptions.py](https://github.com/encode/httpx/blob/b5addb64f0161ff6bfe94c124ef76f6a1fba5254/httpx/_exceptions.py)；[官方 transport 文档](https://www.python-httpx.org/advanced/transports/)说明可配置重试只覆盖 ConnectError/ConnectTimeout。实现显式 retries=0、verify=True、trust_env=False、follow_redirects=False。采样 master 不是运行时版本锁；运行依赖需选稳定发行版。 |
| OpenAI Python `1a90f1c3242307d4654924c3c088759e9655aaa3`，Apache-2.0 | key/base_url/model、images edit、models list、multipart | 可用，但非必要；默认两次重试及统一异常转换会掩盖严格分类。[_constants.py L8](https://github.com/openai/openai-python/blob/1a90f1c3242307d4654924c3c088759e9655aaa3/src/openai/_constants.py#L8)；[_base_client.py L885–924](https://github.com/openai/openai-python/blob/1a90f1c3242307d4654924c3c088759e9655aaa3/src/openai/_base_client.py#L885-L924)对408/409/429/5xx重试；[L1147–1183](https://github.com/openai/openai-python/blob/1a90f1c3242307d4654924c3c088759e9655aaa3/src/openai/_base_client.py#L1147-L1183)对超时/请求异常重试。若复用必须 max_retries=0 并保留底层异常 cause。该采样 main 已含 httpx2 兼容层，不能把当前 main 等同环境已装版本。 |
| LiteLLM `6d4fa56ac434c392dc34442f752272087eddcbbc`，MIT（enterprise 例外） | 多厂商 image_edit、api_base/api_key、异步 API、厂商轮询实现、Router 配置回退 | 成熟但当前不作为执行核心。image_edit 接口接受 base/key 等 kwargs：[images/main.py L711–754](https://github.com/BerriAI/litellm/blob/6d4fa56ac434c392dc34442f752272087eddcbbc/litellm/images/main.py#L711-L754)。Router 在通用异常后走回退：[router.py L7859–7924](https://github.com/BerriAI/litellm/blob/6d4fa56ac434c392dc34442f752272087eddcbbc/litellm/router.py#L7859-L7924)，num_retries=0只关闭重试，不自动关闭 fallbacks。BFL 编辑先 POST 后内置轮询：[handler.py L189–208](https://github.com/BerriAI/litellm/blob/6d4fa56ac434c392dc34442f752272087eddcbbc/litellm/llms/black_forest_labs/image_edit/handler.py#L189-L208)，上层需要分辨轮询失败与未提交失败。没有从所核对路径证实可直接满足跨进程接受状态持久化。 |
| Portkey Gateway `669825cbe89ee51569918b8f78a9db486fd69dd4`，MIT | multipart images/edits、provider/key/customHost、嵌套配置回退、可选状态码 | 是需要独立轻网关时最贴近的候选，但当前不引入独立服务。[imageEditsHandler.ts L16–30](https://github.com/Portkey-AI/gateway/blob/669825cbe89ee51569918b8f78a9db486fd69dd4/src/handlers/imageEditsHandler.ts#L16-L30)调用通用 targets；[handlerUtils.ts L662–690](https://github.com/Portkey-AI/gateway/blob/669825cbe89ee51569918b8f78a9db486fd69dd4/src/handlers/handlerUtils.ts#L662-L690)没有 onStatusCodes 时对所有非成功响应继续回退；[retryHandler.ts L26–42](https://github.com/Portkey-AI/gateway/blob/669825cbe89ee51569918b8f78a9db486fd69dd4/src/handlers/retryHandler.ts#L26-L42)把本地 Abort 超时转为408，[L182–205](https://github.com/Portkey-AI/gateway/blob/669825cbe89ee51569918b8f78a9db486fd69dd4/src/handlers/retryHandler.ts#L182-L205)把其他 fetch 异常转500。默认 retries attempts=0：[requestContext.ts L148–154](https://github.com/Portkey-AI/gateway/blob/669825cbe89ee51569918b8f78a9db486fd69dd4/src/handlers/services/requestContext.ts#L148-L154)，但广义 fallback 仍需禁用。modelsHandler 包含 control-plane 路由，不是完整的本地能力发现保证。 |
| new-api `1d4328e97417a043a161a0dd30a5b129be3ace49`，AGPL-3.0 | images edits、channel/key/model映射、models routes、多类异步任务和计费后台 | 功能广，非轻量节点依赖。图片 DoRequest 错误映射为500：[image_handler.go L134–149](https://github.com/QuantumNous/new-api/blob/1d4328e97417a043a161a0dd30a5b129be3ace49/relay/image_handler.go#L134-L149)；[controller/relay.go L149–212](https://github.com/QuantumNous/new-api/blob/1d4328e97417a043a161a0dd30a5b129be3ace49/controller/relay.go#L149-L212)依请求策略重新选择频道重试。其任务提交路径另有计费/持久化生命周期（L462起），不能据此推断任意图片上游已有防重复协议。 |
| one-api `8df4a2670b98266bd287c698243fff327d9748cf`，MIT | channel、models、图像生成 | 排除编辑核心：[/images/edits 明确 RelayNotImplemented，router/relay.go L27–29](https://github.com/songquanpeng/one-api/blob/8df4a2670b98266bd287c698243fff327d9748cf/router/relay.go#L27-L29)。[controller/relay.go L105–121](https://github.com/songquanpeng/one-api/blob/8df4a2670b98266bd287c698243fff327d9748cf/controller/relay.go#L105-L121)默认允许429、5xx及多数其他状态的重试，非防重复提交策略。 |

## 新增 ComfyUI 图像节点对照

- **lceric/comfyui-gpt-image**：SHA `77b621c871059df2613eafc64130f05a23882a1f`，MIT。可作为 ComfyUI 图片转换/multipart 语义参考；[nodes_api.py L225–319](https://github.com/lceric/comfyui-gpt-image/blob/77b621c871059df2613eafc64130f05a23882a1f/nodes_api.py#L225-L319)确实实现 api_base/auth_token/model、单图 image、多图 image[] 和 mask。client 设置 timeout 后发送一次请求，但没有四家回退、模型能力校验及接受任务持久化。该节点输入可调整大小；严格输入保真需求不能未经判断照搬。
- **magicwang1111/ComfyUI-GPT-image**：SHA `4d81bf9e741786de64761024a83cf771d88f20f7`，snapshot metadata license=null，未发现 LICENSE；仅研究，不复制。[py/api/client.py L9](https://github.com/magicwang1111/ComfyUI-GPT-image/blob/4d81bf9e741786de64761024a83cf771d88f20f7/py/api/client.py#L9)默认重试一次，[L55–63](https://github.com/magicwang1111/ComfyUI-GPT-image/blob/4d81bf9e741786de64761024a83cf771d88f20f7/py/api/client.py#L55-L63)包括 ReadError/RemoteProtocolError；会在可能已接受后重复提交，不直接复用该策略。
- **Latentnaut/ComfyUI-Gemini3-API-Fallback**：SHA `889d5bb29ee9b7dc51c8ac938a4b7513f714d11c`，snapshot metadata license=null，未发现 LICENSE；仅研究，不复制。[gemini_node.py L1033–1059](https://github.com/Latentnaut/ComfyUI-Gemini3-API-Fallback/blob/889d5bb29ee9b7dc51c8ac938a4b7513f714d11c/gemini_node.py#L1033-L1059)对断连及多数异常转下一 key/下一轮；该策略与不重复付费提交相冲突。

## 许可证边界与复用义务

HTTPX 的 BSD-3-Clause 要保留版权/许可/免责声明，不能用作者名背书；MIT 候选保留版权/许可文本。OpenAI SDK 的 Apache-2.0 要保留许可证/适用声明并标明修改（若随包分发修改版）。LiteLLM 根 LICENSE 明确 enterprise 目录单独许可；GitHub NOASSERTION 不表示整个项目闭源，也不等于全目录MIT。new-api 的 AGPL-3.0 不是禁止使用，但把其代码改作/合入并对外提供网络服务可能带来提供对应源码的义务；当前不复制它。无许可声明的节点不按“公开即自由复用”处理。许可证说明仅用于工程选择，不替代法律意见。

本实现应通过 pip 依赖复用 HTTPX/Pillow，不内嵌候选仓库代码；研究快照仅留在 research，不打包为节点。模型列表仅证明 identifier 可见，不证明支持 image_edit/mask/价格；运行应取配置能力白名单，discovery只辅助刷新并提示未确认项。
