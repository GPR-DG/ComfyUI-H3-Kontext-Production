# 第三方代码与许可证边界

自有适配器代码：MIT，完整文本在 LICENSE。

实际复用通过pip安装的发行库，未复制上游候选实现：
- HTTPX 0.28.1：BSD-3-Clause，原文副本 licenses/httpx-0-LICENSE.md。
- 本次测试环境 Pillow 12.3.0：发行版许可证自称 MIT-CMU，原文副本 licenses/pillow-0-LICENSE。部分旧资料标HPND，交付以发行版原文为准。
- NumPy/PyTorch/aiohttp来自用户现有ComfyUI依赖；本包没有捆绑二进制框架。Python SQLite为标准库。

研究而未合入：Mask-External-Edit和HttpRequestNodes实际MIT；UniAPI仅README声明MIT，缺真实LICENSE；LiteLLM非enterprise部分MIT；Portkey MIT；new-api AGPL-3.0；one-api MIT且源路由明确不实现image edits；其余无许可证候选不复制。详情见CANDIDATE-EVIDENCE/GATEWAY-EVIDENCE固定SHA及公开源链接。

研究快照在完整项目research，仅供取证，不作为本节点运行依赖，也不进入安装ZIP。未把第三方仓库“公开可读”等同许可可合入。未修改或分发任何H3 Core/Z-Image/Background Core原始文件。
