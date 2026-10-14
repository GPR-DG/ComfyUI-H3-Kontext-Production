# ComfyUI-H3-Kontext-Production

RunningHub / ComfyUI 单仓部署包，版本 **0.1.0**。一次加载原 H3 Core、API、A2 和 H3K Kontext 节点；不重写算法，不修改原项目或正式工作流。

## 安装

在支持安装自定义 Python 插件的 ComfyUI / RunningHub 实例中，将本仓库的 `feature/rh-production-package` 分支安装到一个 `custom_nodes/ComfyUI-H3-Kontext-Production` 目录，使用该实例的 Python 安装根目录 `requirements.txt`，然后重启。

```bash
git clone --branch feature/rh-production-package https://github.com/GPR-DG/ComfyUI-H3-Kontext-Production.git
python -m pip install -r ComfyUI-H3-Kontext-Production/requirements.txt
```

不要与旧 H3HardCutRunner、H3-Adapter、Kontext-BackgroundBridge 插件同时启用，避免同名注册及 API 路由重复。安装前记录旧插件状态；本包不会自动删除或修改它们。

H3K 本地链路不需要 API 配置。如果使用保留的 H3 API/A2 功能，按原 Adapter 的初始化方式，将 `h3_adapter_bundle/config/providers.example.json` 复制为同目录 `providers.json`（仅首次、文件不存在时），再通过原管理界面配置；不要覆盖已有配置。初始供应商处于禁用状态。

## 精确名称兼容

所有原 class、原注册名、原输入输出保持不变。三个额外注册键直接引用原 class，没有新 class、包装函数或空节点：

| 新增兼容注册键 | 真实原 class |
|---|---|
| H3CBackgroundFinish | H3CBackgroundAttachClean |
| H3StageGuard | H3KStageGuard |
| H3StagePreview | H3KStagePreview |

**H3CBackgroundFinish 保持 AttachClean 的接口**：必填 `task/view/clean_background/wash_token`，可选 `removal_mask`；输出 `BACKGROUND_VIEW/IMAGE/STRING`。它不是 H3KBackgroundFinish 的七输出接口，也不声称找到了同名独立 class。

## 固定来源

- H3C：GPR-DG/ComfyUI-H3HardCutRunner，`e1516896fb2b90e66b9d3ae811a5004cb5ff5626`。
- H3K/API/A2：GPR-DG/ComfyUI-H3-Adapter，`687c052fb2d5cb618a763c5ab8cc672df1295d1b`，H3K 0.1.8。
- 两个子目录内文件直接取自 Git 对象，逐文件校验 GitHub blob SHA 与 SHA256，见 `UPSTREAM-MANIFEST.json`。不是历史交付副本。
- 子目录的历史说明仅描述其原仓库；本包本轮结果以根目录 `verification/` 和本 README 为准。

## 验证与范围

本包负责最终指定的 14 个注册名称及其原 H3 依赖。完整原工作流还需要已存在的 MiniMax/YCNodes、SelfLift、EasyUse、DepthCrafter、Qwen、KJNodes、VHS、Essentials 等插件及模型，**本仓库不替代这些依赖、不包含模型权重**。

CPU 合成图像测试仅验证加载、接口、缓存、处理状态、lazy 调度和清理；不证明人物消除质量、模型推理效果或 RunningHub 云端实机可用。

节点清单见 `NODE-INVENTORY.json`；测试证据见 `verification/TEST-RESULTS.json`。源码完整性可运行 `python -m unittest discover -s tests -v`，需要满足运行依赖。

本轮实测：317 项 Python 测试、6 个 JavaScript 测试文件全部通过；真实 ComfyUI 前端导入原 JSON 的 132 个节点，注册缺失为 0。为完成全图加载核对，原底座第三方插件只安装在隔离测试宿主，没有混入本包。测试宿主未安装推理模型，所以保留模型选择验证警告，未执行完整视频生成。
