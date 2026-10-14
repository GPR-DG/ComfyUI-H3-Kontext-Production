# H3 Adapter 设计与执行计划

用户已明确授权自主选型并开始正式开发，不重复设置设计确认关卡。范围：第一阶段仅 IMAGE/MASK 图像编辑；不得改 H3/Z-Image/Background Core，不调用收费 API。

## 选型（先源码后实现）
- 三候选固定提交与源码路径详见 research/candidate-evidence.md；根代理已直接读取 Mask nodes.py:429、HttpRequest rest_api_node.py:78-141、UniAPI uni_api_node.py:172 附近。
- 使用 HTTPX（BSD-3-Clause）做成熟 HTTP/multipart/TLS 传输；Pillow（MIT-CMU，以发行版 LICENSE 原文为准）做图像编码。自有补充代码 MIT。未复制无许可证的 UniAPI；不嵌入完整 Gateway。
- 不使用 SDK 默认重试；不绕过证书校验。SQLite（标准库）记录已提交、已受理、不明状态和结果；这部分是安全付费切换的必要差异，非重造通用 Gateway。

## 模块/调用图
画布 H3ImageEdit → ConfigStore（外部配置/环境密钥）→ Engine（能力筛选/优先主备/预算/冷却/请求记录）→ Protocol（multipart或声明式JSON/上传/异步查询/下载）→ Pillow验证 → IMAGE。
管理界面 → 本地/管理员认证 routes → ConfigStore / Protocol.discover。工作流只保存逻辑模型别名和供应商引用，不保存密钥/地址。

## 核心约束
1. primary + 可扩展 fallbacks；手动 provider 固定时不切换。只匹配 image_edit、mask、多图能力，不自动推断模型能力。
2. 模型发现只使用显式配置的正式API路径；无discovery依然可手填。
3. POST只提交一次；仅连接前失败或明确非受理HTTP拒绝才切换。读写超时、5xx、成功响应解析失败都视为不明，禁止自动跨商再付费。
4. 已受理异步任务只GET查询；超时/下载失败可按相同请求恢复，禁止重复POST。终态失败也不自动再付费。
5. 相同输入+nonce得到稳定请求ID；持久结果复用。新付费任务必须显式增加nonce。不承诺跨不同安装目录的全局幂等。
6. 费用是用户配置的保守估计/预留，不是供应商账单硬上限；未知费用在有限额时不调用。多次安全拒绝释放预留；不明/已受理保留。
7. Key只在环境变量或服务端私密文件；管理API不回传，HTTP异常不带原始响应、URL、Key。证书校验固定开启。
8. RH云端未知项诚实记录，不将本地模拟测试写成实机成功。

## 执行任务/验收
- [x] 配置验证/密钥存储：先失败测试，再实现；四商配置样例。
- [x] 协议层：独立代理源码取证后TDD，实现同步multipart、JSON模板、上传及异步查询。
- [x] 调度记录：TDD实现主备、有限尝试、冷却、模型映射、费用、状态恢复/防重复提交。
- [x] Comfy节点/管理界面：保持标准IMAGE/MASK与稳定逻辑别名，后端认证接口，前端搜索刷新。
- [x] 免费本地HTTP模拟闭环、异常和异步恢复测试；Comfy接口/工作流schema验证。
- [x] 新鲜独立代码评审、修复关键问题、全套测试、ZIP安装包/哈希/来源/交接文档。

## 需真实环境补齐
SubRouter明确图像编辑接口文档、模型真实ID/能力、正式发现API和报价；RH收录/安装权限、HTTPS外连、服务端秘密存储与实机输出。无真实Key授权，本轮不发送付费请求。

完成标记指源码与免费模拟验证，不代表真实Comfy/PyTorch/RH云端或付费模型已验证；完整边界见VALIDATION.md。
