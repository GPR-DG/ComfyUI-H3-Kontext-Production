> 历史说明：本文原验证计数/审查对应 0.1.0；当前 0.1.1 结论和独立发行包回归见 AUDIT-ROUND2.md，不能将旧计数视为现版验收。

# 独立评审与修复证据

日期：2026-10-10。范围：ARCHITECTURE.md，h3_adapter/config.py、ledger.py、engine.py、routes.py、protocol.py；并核对节点契约、mask 编码与前端管理控件。评审代理不修改生产核心，独立回归仅写 tests/test_review.py；修复由对应实现代理完成。

## 最终新鲜验证

在 ComfyUI-H3-Adapter 目录，TEMP/TMP 指向项目 work/tmp：

```powershell
..\work\venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/test_frontend.mjs
node --check web/h3_adapter.js
```

本评审代理实际重跑结果：**70 个 Python 测试，69 通过、1 明确跳过、0 失败**（6.762 秒，退出码 0）。前端契约测试通过，JavaScript 语法检查退出码 0。独立 test_review.py 的 12 项回归全部通过。没有真实 Key、付费 API 或 RH 任务调用。

唯一跳过项是 Real PyTorch 不在环境中，无法执行标准 BHWC Tensor / 实际 ComfyUI 运行检查。跳过不是通过；按主执行记录，CPU PyTorch 安装因可用空间不足失败，因此真实 Torch / ComfyUI 仍待验收。

## 本轮实际发现并修复

| 问题与原始失败证据 | 最小修复 | 回归结果 |
|---|---|---|
| 并发 save_key 共用 .tmp，实际出现 PermissionError，且旧读改写会丢另一个供应商密钥 | UUID 临时文件；保存秘密之前用跨进程标准库文件锁包住整个读改写 | 线程与真实 spawn 双进程保存均保留两个独立 Key |
| 云反代连接在后端显示 loopback 时，无令牌可管理；模拟 Host cloud.example / 同源 Origin / 外部 X-Forwarded-For 得 200，预期 403 | 无令牌仅准入真正 loopback Host / 无转发信息的本地管理；远端需显式管理员令牌 | 反代边界测试 403；原本地管理测试仍通过 |
| async:true 导致 bool.get AttributeError，配置接口实际返回 500 | 嵌套协议对象 / 数字等类型先验证，配置错误返回 400 | 不合法配置回归通过 |
| 配置把 5xx 放入安全拒绝码时会允许跨商再次提交，违反模糊受理不重复付费约束 | 配置限制安全码为有正式非受理依据的 4xx；协议无条件将 5xx 视为不明 | 协议与 Engine 500 不切备测试通过 |
| 未知报价实际成功 / 缓存 / 模糊重放 / 失败任务重放显示 0.0，不是真正已知零费用 | 从持久 snapshot 的模型报价恢复 estimated_cost，保留 null | 四种报告路径保持未知；无重复 POST |
| 已有未知费用任务后启用累计上限，新 nonce 又成功提交，实际新增一次模拟付费 POST | 有限累计预算不能把历史未知的已受理 / 不明 / 已完成费用当零；保留记录并阻断新预留 | 新请求 blocked，模拟付费 POST 仍仅一次 |
| 上传、mask 上传与编辑重复使用整段超时时间，可能超过总预算后仍提交 | 一个提交阶段 deadline，各操作读取剩余时间 | 共享 deadline / 过期不发编辑 POST 回归通过 |
| 强制 64 KiB iter_bytes 缓冲让细小滴流掩盖总 deadline；0.015 秒预算实际用了 0.235 秒 | 取消人为分块聚合，用自然流块逐次检查总时间与响应大小 | 小块慢流独立 deadline 回归通过 |

本轮以上可重现关键问题已修复并以新鲜测试确认；不是对所有供应商、所有部署或系统安全的全面担保。

## 计费 / 并发 / 恢复的独立证据

tests/test_review.py 包含：

1. 相同输入 + nonce 的两个真正 spawn 进程，共享同一 runtime SQLite：模拟付费 POST **一次**，至少一个执行成功。
2. 不同 nonce 的两个进程，同一累计上限 0.1、单次估计 0.1：模拟付费 POST **一次**，状态 success + blocked。SQLite 预留先于提交。
3. 不同供应商的秘密并发保存：文件锁保护完整读改写，两个秘密都留下；没有 getter 返回明文。
4. 已受理异步任务跨 Engine 实例恢复：POST **一次**，同一任务 GET **两次**，最终成功。
5. 未知报价的成功 / 缓存 / 模糊与终态重放保持 null；启用有限预算后不掩盖旧的未知消费。
6. 总时限小块慢流、云反代管理拒绝和嵌套配置错误边界。

其他测试同时覆盖只在明确非受理时切换、手动供应商不切备、能力 / mask / 多图筛选、冷却、持久预算与请求复用、下载白名单且 CDN 不带 Key、异常不回显供应商内容和秘密、真实 HTTP 本地模拟闭环。

已受理与不明状态不能靠删除 runtime 记录重新提交；防重复保证限于共享该 SQLite / 安装运行目录，不承诺跨不同目录或主机的全局幂等。费用限额仍是人工声明的保守估计和预留，不是供应商账单的硬上限。

## 前端明确需求验收

前端测试在模拟 ComfyUI hook / API 环境执行；另用真实浏览器 DOM、仅 stub api.fetchApi 做无网络冒烟：

- provider / model_alias 保持普通 STRING；管理按钮与报告不序列化。
- Key 与管理令牌只在独立 password 弹窗内处理，不进工作流、浏览器持久存储或公开配置；保存后清空。
- 发现列表支持搜索与手工实际 ID；只修改模型 ID，不从目录猜 image_edit / mask 能力。
- 新增供应商默认 disabled，生成独立 key_env；启用 checkbox 需保存。删除修正 primary / fallbacks 并禁止删除最后一个。
- 删除配置不删除旧 Key 或 Journal；已受理任务恢复仍需旧密钥。
- 报告用 textContent；文本形似 HTML 也不会被解释执行。

## 仍待真实环境验证

- 真实 PyTorch IMAGE/MASK Tensor 与完整 ComfyUI 加载 / 执行；当前 only schema / Pillow / mocks，不称实机出图。
- RH 中国站的节点收录、任意自定义 Python 安装权限、WEB_DIRECTORY 与路由可用性、指定 HTTPS 域名出站、秘密隔离和实际服务器任务输出。
- 严格同源检查比较后端 request.scheme / Host；HTTPS 反代到 HTTP 后端时，平台须正确保留原始 scheme / 路由。RH 如何实现未验证，不称通用云端即装即用。
- 真实供应商的模型 ID、编辑 payload / mask 编码、下载域名、发现 API、正式报价及受理语义；SubRouter 大陆服务限制见 RUNNINGHUB.md / 研究证据。

不以本地 mock 输出、HTTP 提交成功或 skipped 项替代上述证据。
