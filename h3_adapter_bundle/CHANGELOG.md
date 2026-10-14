## 0.1.8 — H3K 源码补齐（2026-10-14）

- 从本地真实独立 Bridge 纳入八个 H3K 类并由 Adapter 根注册，旧 API/A2/前端字节保留；Core 不改。
- 复现后修复 LF/CRLF Core pin、geometry/IMAGE proof 别名、READY 文本覆盖和结束任务的 H3K 内存保留。
- 调用内合并重复 Recipe 文件读取，READY 后释放 Z proof；保留 Kontext 6 步、Qwen、Z、两阶段预览和任务合同。
- 交付边界、逐节点审核、优化对比、测试限制与 RH 安装说明：docs/H3K-DELIVERY.md。

## 0.1.7 — 独立取证与两轮复审（2026-10-13）

修复备用配置重复付费身份、账号缓存/恢复授权、压缩流上限、ComfyUI 失败图像阻断与 Finish READY 提交顺序。技术摘要从模型 Prompt 移入 nonce；旧账本新请求默认迁移审查，完整防重及六源码校验保留。前端与正式工作流不改；集成示例仅更新版本/哈希元数据。测试与部署边界见 docs/AUDIT-017.md。

## 0.1.6 — 2026-10-12

- 根包统一注册现有 H3ImageEdit 和七个 A2 BackgroundBridge 节点，保留 WEB_DIRECTORY、路由、API 接口和前端原文件。
- 纳入二次取证的宽高比 Guard；Recipe 与当前 ConfigStore 快照/凭据代际接口兼容，捕获凭据时验证同一配置版本。
- 保留并重新生成六文件 SHA256 校验，LF 属性确保 Windows/Linux 字节一致；补充 NumPy 运行依赖。
- 交付原样 nodes/links 的 121/251 融合图、RH 同仓库安装说明和节点类型清单；发布 allowlist 包含 Bridge 与工作流。
- 验证范围和已知 API 限制见 docs/INTEGRATION-VALIDATION.md；未验证 RH 云端。

# Changelog

## 0.1.5 — 开发测试候选增量更新（2026-10-12）

- 修复非 ASCII 管理令牌的服务端异常与前端坏缓存；拒绝后可以重新授权。
- 同窗口密钥写入串行化，关闭窗口后忽略迟到反馈。
- 配置落盘成功后保留成功提示、revision 和用户未保存编辑，单独报告 Key 刷新失败。
- 结果临时文件在写入/替换异常时清理；保持 result_ready 与同任务恢复，不新增 POST。
- 保留配置 revision、凭据代际、身份冷却和模型/供应商切换参数清理，原测试不改。
- 新增授权回归与 4 类前端回归，更新公开审计、源码导航、验证与发行边界。
- 当前 Python 171/171、6 套 JS 和 27 类 TCP Mock 通过，3 项 Git 写入夹具明确排除；实际宿主成功路径通过，失败 IMAGE 消费仍有缺陷。
- 已知解压前分配与空 IMAGE 传播问题尚未修复；开发测试候选，Stable Release NO。

## 0.1.5 — 最终独立源码审计修复（2026-10-11）

- 修复配置读取与凭据读取之间的并发修改：提交和模型发现使用锁内配置 revision，拒绝旧配置借用新供应商的 Key。
- 任务快照记录非秘密 credential_generation；恢复时区分连续身份轮换与删除重建，阻止旧环境 Key 任务使用新身份的 Key。
- 冷却记录按地址、认证身份和代际匹配；旧数据库平滑增加可空 identity 列，保留旧任务记录和保守冷却。
- 供应商、模型 ID 或别名实际变化时清空节点 parameters；选择未变保留用户参数。
- 新增 8 项 Python 回归、6 个前端回归场景，以及使用官方 ComfyUI 宿主和本地 Mock 的导入/IMAGE 消费验证脚本；原测试未改。
- 新增 SOURCE_MAP、FINAL_AUDIT_REPORT、RELEASE_CHECKLIST，更新安装与协议说明，发行白名单收录本次文档与验证文件。
- 仍使用原 H3ImageEdit 节点、输入输出合同、nonce 语义、主备调度和 SQLite 提交预留流程。真实商家/RH 与目标 Windows 存储环境仍须验收。

更早的版本历史见 docs/CHANGELOG.md；其中旧 PASS/计数不代表本次源码结论。
