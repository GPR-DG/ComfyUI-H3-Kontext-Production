> 当前版本 0.1.7（2026-10-13）的独立结论和实际测试见 [AUDIT-017](docs/AUDIT-017.md)。下文保留历史记录，其中旧版本“未修复”说明不代表本版；GitHub/RH 状态以实际交付报告为准。

# RELEASE_CHECKLIST

版本 0.1.5，2026-10-12。开发测试候选可上传；Stable Release：NO。以下是当前合并版本验证，不复用历史测试计数。

## 本次范围

- [x] 对照现有 main 基线，保留现有历史和其余源码，只增量修改明确文件。
- [x] 修复管理 token 错误处理、密钥保存竞态、配置成功提示和结果临时文件清理。
- [x] 保留配置 revision、credential_generation、health.identity、参数切换清理与原回归。
- [x] H3ImageEdit 名称、输入输出、nonce、主备调度和持久账本流程保持。
- [x] SOURCE_MAP、README、CHANGELOG、FINAL_AUDIT_REPORT 与验证说明更新。

## 实际免费验证

- [x] Python 174 发现、171 执行/通过，0 失败/错误/跳过；3 项 Git 写入夹具依既有约束排除并在报告列出。
- [x] 5 套原 JS 和 1 套新增回归通过，原断言未改。
- [x] 27 类真实 TCP Mock：重复、主备、预算、未知不切换、恢复与请求字段。
- [x] 实际 Chromium 与生产路由验证 token、无效未保存编辑和密钥串行响应。
- [x] Windows 只读替换失败清理和一次 POST 同任务恢复。
- [x] 实际 ComfyUI CPU 宿主导入、路由、有/无 MASK、成功缓存与消费者通过。
- [x] 已知缺陷复现如实记录：解压前分配；五类无图状态的标准消费者 IndexError。
- [x] 精确发行白名单、禁用占位配置、manifest、CRC、成员 hash 核对。

## 公开上传

- [x] 目标是现有 GPR-DG/ComfyUI-H3-Adapter；凭据和 push 权限由当次 API 读取确认。
- [x] 不提交活动配置、真实 Key/Token、私密日志、DB、runtime、用户图片、本地证据或候选 ZIP。
- [x] 测试中合成不可用凭据仅作为 fixture 保留。
- [x] 逐文件核对 diff/status，明确暂存名单，只提交所列公开文件。
- [ ] 发布完成事实由实际远端 SHA 核对后在交付回复中报告；本清单不能代替上传证据。

上传使用用户指定标题 `release: ComfyUI H3 Adapter initial stable audit release`；正文明确 `Development candidate; Stable Release NO`。Git 传输失败时，可用已授权 GitHub API 创建同仓库增量 tree/commit；推进 main 必须为普通快进，禁止强制更新。分支保护失败时保留错误并改用同仓库审核分支。不建替代仓库、不创建稳定标签或 Release。

## 稳定发布阻断与未验收

- [ ] IA01：解压前内存分配限制。
- [ ] IA02：无图状态到标准 IMAGE 消费者的失败传播。
- [ ] 真实供应商协议、模型能力、safe rejection 语义与实际账单。
- [ ] 编辑质量、RH 部署、外连、租户/Key 与持久卷闭环。
- [ ] 特殊 Linux 锁路径、SQLite 长锁、硬退出残留及目标 Windows ACL/文件锁。
- [ ] 其他 ComfyUI/平台/Python/GPU 组合。
