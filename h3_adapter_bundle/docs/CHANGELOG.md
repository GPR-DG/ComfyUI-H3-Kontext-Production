# 变更记录

## Unreleased

## 0.1.5 — 2026-10-11

- [修复] atomic_json 在序列化/fsync/replace 失败时清理本次临时文件，保留原数据并报告失败。
- [修复] 删除供应商后退役旧 Key，复用 ID 需独立新 Key；凭据指纹匹配可恢复原付费任务。
- [修复] 删除/重建相同配置的 revision 纳入解绑代次，拒绝旧窗口回写；public/保存返回 revision 同锁快照。
- [修复] ConfigStore 内部读取与写入共用原锁，消除真实复现的 Windows reader/replace 竞争，无额外重试。
- [验证] 新增11项针对性测试和27类独立真实TCP冒烟；真实CPU ComfyUI有/无Mask、Preview/Save、重启缓存与浏览器管理通过。
- [交付] 发行白名单加入针对性测试、独立冒烟脚本和补充报告；公开文档个人路径泛化，原始历史备份保留。
- [限制] 真实商家、账单、RH云端和历史随机WinError5每次具体根因未验证；不标生产稳定版。

## 0.1.4 — 2026-10-11

- [修复] 构建改用精确文件白名单，避免非标准秘密/备份文件进入 ZIP；启用的 example 在 ZIP 写入前拒绝，安装 active config 仍来自禁用 example。
- [修复] 非法 multipart image/mask/upload 字段在 HTTP 发送前拒绝，避免本地构造错误误占付费未知记录；释放主家预留、不冷却健康主家，合法备用可继续。
- [调整] JSON 常量模板继续合法；报告提示未映射模型、提示词与非空参数，并在缓存/异步恢复中保留提示。
- [调整] Git 忽略非公开 config、备份、日志、临时文件与 DB 伴随文件；不替代实际暂存审查。
- [验证] 新增 11 个回归方法，旧 143 项测试原样保留；源码最后一套 154 项，153 pass / 1 Torch skip。Windows os.replace 拒绝访问在其他运行中仍复现，根因 UNVERIFIED。
- [限制] 真实 Torch、完整 ComfyUI、商业 API、真实账单与 RH 实机未验；不发布生产稳定性声明。

## 0.1.3 及以前

历史实现与证据分别见 AUDIT-ROUND4.md、AUDIT-ROUND3.md、AUDIT-ROUND2.md。历史计数不作为 0.1.4 验收。
