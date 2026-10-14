> 当前版本 0.1.4。第五轮独立审计见 AUDIT-ROUND5.md；最终源码全套 154 项：153 pass、1 真实 Torch skip。此前完整回归和重复检查仍复现 Windows os.replace 的 WinError 5，根因及目标存储稳定性 UNVERIFIED，不能用通过重跑覆盖失败证据。包内结果以第五轮报告与 audit-round5/package-verification.json 为准。下文旧计数保留为历史。

> 历史说明：本文原验证计数/审查对应 0.1.0；当前 0.1.1 结论和独立发行包回归见 AUDIT-ROUND2.md，不能将旧计数视为现版验收。

# 继续开发交接 / 历史正文 0.1.0（当前 0.1.4）

## 第四轮继续工作前必须知道
- 不按 URL 变化自动清 Key；同 ID/Key 的明确地址迁移允许。新增按钮不再复用已删 ID/主商环境变量。
- ConfigStore.credential 一次捕获一致身份/Key；快照仅存私密 hash。异步原 Key 匹配或身份未变可恢复；legacy 无 hash 且身份已变需还原原条目/Key，同 nonce 继续，不能新付费提交。已经落盘内联/无鉴权下载与 completed 缓存不需要 Key。
- 管理写 Key 携带 revision；兼容脚本省略 revision 不提供旧窗口 CAS。先保存身份，再保存 Key；不要删秘密文件和账本做清理。
- safe_to_failover 与 provider_failure 分离；本地未发送错误可备用但不冷却健康主商；连接失败/配置允许的远端拒绝仍冷却。unknown/accepted 状态与费用预留不变。
- Git 仓库根是插件目录；clone/source ZIP 首次依 README 复制 example，不能覆盖已存在 config。默认 runtime/秘密/env 不分享，自定义路径另行保护。
- WinError5 曾在独立 targeted 回归中出现，后续完整/限定重跑通过但根因未确定；完整首次 traceback 保留，不用 sleep/retry 掩盖。生产仍需目标环境写文件稳定性验证。

## 任务边界
所有交付只在桌面 h3适配器；没有读写/修改 H3主链、Background Core 或原始反推洗图JSON。用户禁止收费图像API和未经授权真实Key测试，本轮没有此类调用。目标是一节点、外部配置、可更换供应商，阶段1只图像编辑。

## 先读
README.md → docs/ARCHITECTURE.md → docs/PROTOCOLS.md → docs/REVIEW.md → docs/VALIDATION.md。完整项目research/含候选/网关/RH取证固定SHA和source-hash；安装ZIP只带报告/许可证，不带巨型源码镜像或隔离venv。用户指定D:/codex-ai-skills四个Skill已完整读取：全局看代码逻辑、调Bug、省代码总规则、联网资料过滤器；AnySearch脚本/服务不可用时用现有web官方源取证，未保存任何搜索服务Key。

## 已实现的公共接口
- nodes.py H3ImageEdit：IMAGE/prompt/provider/model_alias/parameters/auto_failover/timeout_seconds/max_cost/request_nonce + optionalMASK → IMAGE,STRING,STRING。
- ConfigStore(path).load/save/public/key/save_key。非秘密providers.json；env优先、secrets.private.json次之；密钥不回传。secret更新有跨进程文件锁和唯一atomic临时文件。
- Engine(store,runtime_dir).edit(...) → {images:[bytes],report:{status,provider,model,request_id,attempts,elapsed_ms,estimated_cost,currency,cached,error}}。
- Protocol：openai_images multipart / json_template；submit/task_id/poll/result_record/result/discover；只一次POST、正式配置发现接口、文件上传、GET任务恢复、result host allowlist/TLS。HTTPX不采用环境代理、不自动重定向、不自动POST重试。
- Journal：SQLite持久claim（先记submitting再POST）、状态/预算/冷却/私密结果；本机不同进程共享记录防重复。不能保证独立云端容器未共享DB时幂等。
- web/h3_adapter.js：添加/删除/启用供应商、JSON/表单、独立Key密码输入、主备JSON配置、搜索刷新/手填模型；管理密码/Key不序列化、不进localStorage。
- 管理routes：默认仅真正本机loopback访问，非loopback/代理需服务端管理token且同源；可环境开关禁用管理。

## 不允许改坏的规则
1. 5xx、读写超时、断连、缺task_id/缺结果、JSON错误：不明、不自动备用重付。已受理任务仅查/下载，终态失败也不自动再提交。
2. 主备只筛显式image_edit/MASK/多图/参数能力；模型发现不得自动证明能力/报价。
3. Key永不放workflowwidget、导出JSON或原始错误日志。私密runtime/secret不能进入ZIP/Git。
4. 相同输入/nonce按稳定ID查缓存/恢复。新收费任务只能用户明确新nonce；删除DB/换目录会失去保护。
5. 价格是配置估计，不是账单。未知费用报告必须null，不是0；有有限cap不得用未知价格。既有未知受理/不明费用阻止后加有限累计cap新提交。
6. 多商仅配置差异，不能复制几套节点/硬编码SubRouter。新增非标准签名协议前先寻找成熟Gateway归一化，不做未来视频架构。
7. 失败是空IMAGE+status，不返回原图伪装修复。标准Comfy MASK白编辑→alpha透明编辑；灰度仅按模型声明转换。

## 验证事实
最终新鲜日志见docs/VALIDATION.md和项目work/validation/。当前70测试：69通过、1真实Torch项跳过；前端契约/语法通过；真实ThreadingHTTPServer演示primary401→backupPNG、相同nonce不新增POST。跨spawn进程相同nonce一次POST、不同nonce共享估计cap、私密Key更新不丢写均验证。

**不是已验证普通ComfyUI进程/RH/真实模型效果。** 为隔离真实进程测试只在work克隆官方ComfyUI（SHA 08ff3c11b3a85eb07c2c06f21cb378ac2e086840）。CPU Torch2.8.0与2.2.2安装均磁盘空间不足，已清除本项目内失败库残留；没有启动真实Comfy进程，没有改用户Comfy。NumPy端口double测试不是Torch运行证据。后继有现成ComfyPython时，应先跑被skip真实Tensor测试再执行最小图。

## 未完成 / 真正接通下一步
- 提供实际供应商正式图像编辑文档、编辑模型ID、mask/多图/费用、发现API；Key经私密途径保存。按已覆盖的HTTP契约填配置后不改节点/工作流；真实模型去人效果需你明确授权一次测试。
- RH确认本插件安装/收录机制、目标API/CDN HTTPS和鉴权外连、服务端秘密与持久卷/多租户策略、前端扩展/管理route是否可加载。
- 在用户自己的Comfy完成LoadImage→H3ImageEdit→SaveImage免费mock图并记录object_info/history/output；有实际授权后再做付费真实编辑；RH再逐项验收，不把taskId当成功。
- 严格Origin/Host管理校验下，TLS终止代理必须由平台正确暴露同源scheme/host；不能伪造代理头跳过授权。RH管理frontend是否可用待平台确认。
- 没有通用gRPC/WebSocket/HMAC签名、自定义异步POST查询、自动翻页模型发现或真实账单核算；不同协议不等于任意新私有协议无适配。当前 JSON模板GET轮询覆盖范围写在PROTOCOLS。

## 文件变化
本项目所有源码/模板/测试均新建，没有对候选仓库源码作修改或合入；只保留取证快照。自有代码MIT，HTTPX BSD-3-Clause、Pillow发行MIT-CMU原文附包。绝不要提交secret/private运行文件。下一Agent运行全套测试后再打包；离线模型效果/RH未知不得改成已完成。
