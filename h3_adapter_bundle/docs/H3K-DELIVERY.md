# H3K 本地源码交付（Adapter 0.1.8）

## 归属与兼容

八个 H3K 节点来自已施工但未上传的独立 `ComfyUI-H3-Kontext-BackgroundBridge`，并非把 H3A2 改名。统一安装入口现在是本 Adapter 根包；`h3_kontext_bridge` 保持业务独立，不调用 `H3ImageEdit`、ConfigStore、收费生成或外部 API。旧 H3ImageEdit、七个 H3A2、管理路由和前端仍保留。不要同时安装旧独立 H3K 插件与本 Adapter，否则 ComfyUI 会出现同名注册竞争。

依赖 H3 Core `feature/background-reference-nodes`，commit `e1516896fb2b90e66b9d3ae811a5004cb5ff5626`。不修改 Core 源码、不重做 H3C。五个 Core 文件采用严格 LF 规范化 SHA256；只忽略 CRLF/LF 差异，任何其他字节修改仍阻断。ComfyUI 提供 Torch；Core 需要 NumPy/OpenCV。

## 八个节点逐个审核

| 节点 | 业务、异常与复用边界 | 性能/资源结论 |
|---|---|---|
| H3KBackgroundResolve | task/candidate 隔离；exact pixels + mask/depth + full recipe 复用；非精确匹配委托原 Core；只输出已 READY 的图 | task 内 exact 索引保留；不改保守环境识别，不伪造人物 mask |
| H3KBackgroundWashClaim | SQLite 认领；同图 fan-out/失败重试共享已拥有 token；外部已认领任务阻断；READY 不派发 | 不新增租约或自动重发；不能把幂等 fan-out 误改成重复任务 |
| H3KBackgroundSource | 仅 PENDING 且自有 token；原帧 RGB、浮点、范围、16MP 上限；官方 Kontext 桶、统一等比例 affine | 私有 geometry 深拷贝，避免输出字典变更篡改所有权证据 |
| H3KStageGuard | 校验 task/token/geometry；Z 必须在 Kontext 后；有限单帧 RGB、原尺寸恢复；禁止替换已完成阶段 | 输出 tensor 与私有证据隔离；允许必要的有界复制，不能以省内存破坏完整性 |
| H3KRecipe | 参数、源文件、模型 stat、removal prompt、denoise、Kontext/Z 全链摘要；缺失节点/循环/缺源码阻断；每次重新计算 revision | 一个调用内同文件只读一次；不跨调用缓存源哈希，不缓存模型推理结果 |
| H3KPromptCapture | 单图 Qwen 一元素字符串列表规范化；空串/跨任务阻断；PENDING 同文本幂等、不同文本拒绝；READY 不可覆盖 | 保留文本，不新增 Qwen 调用 |
| H3KBackgroundFinish | lazy READY 跳过昂贵输入；PENDING 顺序获取 B、Z；核实阶段 token/recipe/像素/文本后才 SQLite 提交 | READY 后删除不再需要的 Z 双图证据；保留 B 以支持预览；同任务 A→B→A 复用 |
| H3KStagePreview | B 已完成但仍 PENDING 时即可以预览；READY 回访不重新运行 Kontext；跨任务/缺证据阻断 | 只读 cache，输出 clone，保留两阶段标准 PreviewImage 合同 |

任务句柄的原 cleanup 被弱引用包装：先执行原 Core cleanup，成功结束后清空 H3K 私有证据；失败不伪装 cleaned，也不删除其他任务。Core 文件和 API 未改。

## 复现后最小修复

1. Windows 原 pin 对 GitHub LF 文件报错：证明五文件 LF 文本完全相同后规范化 hash/pins；没有放弃 pin。
2. Source 返回的 nested geometry 与私有 proof 同对象；修改 x 后 Guard 原先错误接受：存储深拷贝。
3. Guard 返回 IMAGE 与私有 proof 共享 storage：下游原地写入原先能破坏 B，或让修改 Z 通过 Finish：输出 clone。
4. READY 的 Qwen 文本原先可直接覆盖：改为 immutable；PENDING 已完成文本只允许幂等同值。
5. 原 cleanup 关闭 SQLite 后仍保留本任务 H3K 图像：仅扩展任务句柄 cleanup、弱引用避免新增对象循环。

## 有证据的最小优化

- 两端共享同一实现文件的 Recipe 示例：读源 **4 → 1**；递归拓扑、参数摘要内容不变。
- 120×180 测试帧、真实 Kontext 桶：READY 后 Z proof 额外保留 **12,719,232 → 0 字节**。
- 同一夹具：任务结束后 H3K 图像 proof **12,719,232 → 0 字节**。
- 张量别名修复额外复制用于证据完整性；不承诺神经推理时长或 GPU 峰值下降。

## 验证边界

使用真实 ComfyUI PromptExecutor、lazy 调度、PreviewImage 与原样远端 Core 验证 READY/PENDING、同帧多窗口、A→B→A、任务隔离、denoise 改变、奇数宽高和三阶段故障阻断。Kontext/Qwen/Z 神经推理和 H3 视频消费者在调度测试中是显式 CPU 替身；没有模型权重、不调用收费 API，不能声称视觉去人物或 RH GPU 实机验收成功。

目标 JSON 的八类端口与 SHA256 见 `H3K-TARGET-PORTS.json`。原 JSON、H3 底座、Kontext 6 步/CFG 1/euler/simple/denoise 1/guidance 2.5、`ref_image_8`、RGB/Depth 及 124/22/102 不改。无 mask 的非精确环境回访仍按 Core 保守创建新 view，这不是节点交付 Bug，不做冒进修复。

## RunningHub 中国大陆站安装

1. Core：上面的 `feature/background-reference-nodes` 精确 commit。
2. Adapter：包含本交付的 `feature/h3k-kontext-delivery` 分支，精确 commit 见实际发布记录；不要用旧 0.1.7 main 代替。
3. 原底座的全部第三方节点、Qwen3-VL、EasyUse 循环、Kontext/Z/H3 模型维持既有安装。当前任务未登录 RH，未核实其安装授权或收录状态。
4. 重启 ComfyUI 后检查全部八个 `H3K*`、六个背景 `H3C*` 及原 API/A2 节点；不要同时加载旧独立 H3K 目录。

这是一项已测试源码交付，不是 RH 云端 GPU/全视频生成的验收声明。运行免费包测试：`python -m unittest discover -s tests`；Core hash 回归需要 `H3K_CORE_TEST_ROOT` 指向精确 Core。

H3K 阶段证据保存在当前任务句柄中；本目标图使用新 task / :memory:。不承诺跨进程恢复同一 SQLite task 的 Kontext/B/Qwen 证据；不能把原 Core 的持久数据库能力等同于 H3K 模型阶段持久恢复。因目标合同没有此要求，本轮不增设持久化流程。

## 本轮实际免费验收结果（2026-10-14）

- 原 Adapter 0.1.7 基线 192/192；补齐后全部 Python 207/207（新增 H3K 15 项）。
- 全部六套既有 JS 前端回归通过；原 API/密钥配置/前端实现字节不变。
- 真实 ComfyUI 根 loader 同时加载完整原 Core 和最终 Adapter：八个 H3K、原 H3 API/A2 及目标 Core 节点注册通过。
- 合同测试 37 场景（19 成功、18 预期阻断）；官方 Kontext 几何/ReferenceLatent/FluxGuidance 使用真实代码。
- 最终 Adapter 安装进真实 CPU ComfyUI 服务执行器：19 场景（8 成功、11 预期阻断），成功路径两阶段标准 PreviewImage；同帧三窗模型替身各仅一次，A→B→A 各仅两次。
- 原 Core RGB/Depth/window 11 场景（8 成功、3 预期阻断），124/22/102 保留。
- 原目标 JSON 132 节点/270 连线、全八类端口、ref_image_8、EasyUse 展开及原始文件哈希复审通过，106 个受保护节点不改。
- 神经模型视觉效果、GPU 峰值、RH 中国大陆站实机和完整第三方组合未验证；未调用任何收费生成 API。
