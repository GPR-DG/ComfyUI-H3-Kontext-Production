> 当前版本 0.1.4。第五轮独立审计见 AUDIT-ROUND5.md；最终源码全套 154 项：153 pass、1 真实 Torch skip。此前完整回归和重复检查仍复现 Windows os.replace 的 WinError 5，根因及目标存储稳定性 UNVERIFIED，不能用通过重跑覆盖失败证据。包内结果以第五轮报告与 audit-round5/package-verification.json 为准。下文旧计数保留为历史。

# 最终验证记录（2026-10-10，Asia/Shanghai）

## 当前证据 / 不互相替代
| 项目 | 结果 |
|---|---|
| 源码与配置实际落地 | 是：一个H3ImageEdit、四家模板、动态管理、IMAGE/MASK端口、两协议及上传/异步恢复 |
| 单元/真实loopback HTTP/跨进程测试 | 70项：69通过，1项真实Torch测试明确skipped；0失败，退出0 |
| 前端契约/JS语法 | 通过，退出0；新增/删除/启用、密钥密码框清空、不序列化、模型搜索/手填、报告 |
| 前端浏览器DOM冒烟 | 独立代理真实浏览器执行源JS，但api.fetchApi为mock；不是实际ComfyUI前端加载 |
| 独立mock配置闭环 | 使用providers.mock.json：p0的401→p1返回已知蓝色PNG；重复nonce缓存命中，POST总数仍2 |
| Python编译检查 | compileall h3_adapter/nodes/__init__退出0 |
| 模拟服务器CLI | --port0 --duration0.1退出0；仅127.0.0.1，无付费/真实Key |
| 普通ComfyUI完整进程 | 未执行。隔离CPU PyTorch两次因磁盘空间不足失败；残留只在本项目清理 |
| 真实图像编辑API/去真人效果 | 未执行；缺正式供应商编辑契约/模型/价格/明确付费授权 |
| 大陆RunningHub收录/允许安装/外连/秘密管理/实机 | 均未确认。只完成官方公开资料及现有节点源码取证 |

## 最终验证命令
在包目录，用项目work/venv/Scripts/python.exe：
1. `python -m unittest discover -s tests -v` → Ran70，OK(skipped=1)。
2. `node tests/test_frontend.mjs` → passed，exit0。
3. `node --check web/h3_adapter.js` → exit0。
4. `python -m compileall -q h3_adapter nodes.py __init__.py` → exit0。
5. `python scripts/mock_server.py --port 0 --duration 0.1` → loopback地址，exit0。
TEMP/TMP均指本项目work/tmp。日志在完整交付项目work/validation；安装ZIP内提供摘要，不包含私密运行文件/venv。

实际环境：Windows、Python3.12.14、HTTPX0.28.1、Pillow12.3.0、NumPy2.3.5；PyTorch不可用。未声称Linux/RH或所有依赖版本组合实测。

## 核心行为证据
- 主+3备有序、关闭自动切换、手动固定、禁用/冷却、逻辑模型ID映射；MASK/多图/参数能力不满足不发POST。
- Connect失败与正式拒绝可切换；ReadTimeout、5xx、缺结果禁止备用重付；同nonce跨引擎/真实spawn进程一次POST。
- 已受理async超时/终态失败仅GET/恢复，保留预留；下载/结果错误不重新提交。
- 价格未知在有限cap时跳过；累计cap跨nonce/重启/进程共享；旧未知费用不能在后来设cap后按0忽略；未知费用所有状态报告为null。
- secret跨进程更新无丢写、唯一atomic文件；反向代理loopback不能未授权管理；原始响应/Key不进入报告。
- 5xx无法配置为安全拒绝；受限流解码字节大小、gzip不二次解码；自然响应块检查时限，trickle不能藏在64KiB聚合里。
- MASK白编辑正确转alpha透明；模型声明灰度编码可转换；真实Torch BHWC测试因依赖缺失跳过，NumPy端口double不冒充Torch。

## 本轮修复/未完成
独立评审发现及RED→GREEN：Key并发tmp/丢写、云端代理loopback授权、非法async类型500、5xx绕过防重复、上传多段超时、结果过大、gzip二次解码、未知费用显示0/绕新cap、细碎响应聚合藏deadline。最终12独立review测试全绿，详见REVIEW。

未完成：真实供应商契约/模型能力和费用确认；普通Comfy免费mock实机图及真实Tensor；真实编辑效果；RH审批与实际输出。严格Origin方案需要平台正确处理TLS终止代理scheme/host；不要简单信任外来代理头以放开管理员功能。已实现HTTP契约之外的HMAC/gRPC/WebSocket/异步POST查询/自动翻页不承诺配置即兼容。

安装ZIP与文件manifest由打包脚本校验，无私密Key、runtime、.git、venv、__pycache__或原始H3流程；每个包文件SHA256见SOURCE-MANIFEST.json，ZIP SHA256见releases/SHA256SUMS.txt。
