import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ponytail: one small dialog for config, keys, and picker; no UI framework.
let managementToken = "";

function element(tag, text = "") {
    const el = document.createElement(tag);
    el.textContent = text;
    return el;
}
function input(label, parent, type = "text") {
    const wrapper = element("label", label);
    wrapper.style.display = "block";
    wrapper.style.margin = "8px 0";
    const el = element(type === "textarea" ? "textarea" : "input");
    if (type !== "textarea") el.type = type;
    el.setAttribute("aria-label", label);
    el.style.width = "100%";
    el.style.boxSizing = "border-box";
    wrapper.append(el);
    parent.append(wrapper);
    return el;
}
function button(label, parent, action) {
    const el = element("button", label);
    el.type = "button";
    el.style.margin = "6px 6px 6px 0";
    el.onclick = action;
    parent.append(el);
    return el;
}
function dialog(title) {
    const overlay = element("div");
    Object.assign(overlay.style, { position: "fixed", inset: "0", zIndex: "10000", background: "#000a", display: "grid", placeItems: "center" });
    const panel = element("section");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-label", title);
    Object.assign(panel.style, { width: "min(780px, 92vw)", maxHeight: "90vh", overflow: "auto", padding: "20px", background: "var(--comfy-menu-bg, #252525)", color: "var(--input-text, #ddd)", border: "1px solid #777", borderRadius: "8px" });
    const secrets = [];
    let open = true;
    const close = () => { open = false; for (const el of secrets) el.value = ""; overlay.remove(); };
    panel.onkeydown = (event) => { if (event.key === "Escape") close(); };
    overlay.onmousedown = (event) => { if (event.target === overlay) close(); };
    panel.append(element("h2", title));
    const body = element("div");
    panel.append(body);
    const status = element("pre");
    status.setAttribute("role", "status");
    Object.assign(status.style, { whiteSpace: "pre-wrap", overflowWrap: "anywhere" });
    panel.append(status);
    const closeButton = button("关闭", panel, close);
    overlay.append(panel);
    document.body.append(overlay);
    return { body, panel, overlay, closeButton, status, close, secrets, isOpen: () => open };
}
function askToken() {
    const ui = dialog("H3 管理授权");
    ui.body.append(element("p", "管理令牌只在本页内存中使用，不写入工作流或浏览器存储。云端需管理员显式开启；本机无法代替 RH 部署验证。"));
    const field = input("管理令牌", ui.body, "password");
    field.autocomplete = "off";
    ui.secrets.push(field);
    return new Promise((resolve) => {
        let settled = false;
        const finish = (value) => { if (!settled) { settled = true; field.value = ""; ui.close(); resolve(value); } };
        button("授权", ui.body, () => finish(field.value));
        button("取消授权", ui.body, () => finish(""));
        // Closing a challenge must also resolve its awaiting request.
        ui.panel.onkeydown = (event) => { if (event.key === "Escape") finish(""); };
        ui.overlay.onmousedown = (event) => { if (event.target === ui.overlay) finish(""); };
        ui.closeButton.onclick = () => finish("");
        field.focus();
    });
}
async function request(path, payload, retry = true) {
    const headers = { Accept: "application/json" };
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    if (managementToken) headers["X-H3-Management-Token"] = managementToken;
    const requestToken = managementToken;
    let response;
    try {
        response = await api.fetchApi(path, {
            method: payload === undefined ? "GET" : "POST",
            headers,
            ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
        });
    } catch (err) {
        if (managementToken === requestToken) managementToken = "";
        throw err;
    }
    const denied = response.status === 401 || response.status === 403;
    if (denied && managementToken === requestToken) managementToken = "";
    if (denied && retry) {
        const token = await askToken();
        if (token) { managementToken = token; return request(path, payload, false); }
        throw new Error("管理授权取消；云端管理默认关闭。");
    }
    const textResponse = response.clone?.();
    let data;
    try { data = await response.json(); }
    catch {
        if ((response.status === 401 || response.status === 403) && textResponse) {
            const reason = (await textResponse.text()).trim().slice(0, 256);
            if (reason) throw new Error(reason + "（HTTP " + response.status + "）。");
        }
        throw new Error("管理接口未返回 JSON（HTTP " + response.status + "）。");
    }
    if (!response.ok) throw new Error(data.error || data.message || ("HTTP " + response.status));
    return data;
}
function widget(node, name) { return node.widgets?.find((w) => w.name === name); }
function setWidget(node, name, value) {
    const w = widget(node, name);
    if (w) { w.value = value; w.callback?.(value); }
    node.setDirtyCanvas?.(true, true);
}
function options(select, values, chosen) {
    select.replaceChildren();
    for (const value of values) {
        const option = element("option", value);
        option.value = value;
        select.append(option);
    }
    select.value = values.includes(chosen) ? chosen : (values[0] || "");
}
async function openManager(node) {
    const ui = dialog("H3 供应商配置 / 密钥");
    ui.body.append(element("p", "配置 JSON 无密钥。可添加、删除、改名任意供应商，并配置主备顺序、协议、路径、模型映射和能力。密钥另存服务器；不代表 RH 已安装或运行。"));
    try {
        const data = await request("/h3-adapter/config");
        const editor = input("非秘密配置 JSON", ui.body, "textarea");
        editor.rows = 16;
        editor.spellcheck = false;
        editor.value = JSON.stringify(data.config, null, 2);
        const selector = element("select");
        selector.setAttribute("aria-label", "供应商");
        ui.body.append(selector);
        const id = input("供应商 ID", ui.body);
        const base = input("Base URL", ui.body);
        const env = input("Key 环境变量名", ui.body);
        const enabled = input("启用供应商", ui.body, "checkbox");
        enabled.style.width = "auto";
        const models = input("模型映射 JSON", ui.body, "textarea");
        models.rows = 5;
        const key = input("供应商密钥", ui.body, "password");
        key.autocomplete = "new-password";
        ui.secrets.push(key);
        let selected = "";
        const parsed = () => JSON.parse(editor.value);
        function fill(chosen = selector.value) {
            const config = parsed();
            options(selector, config.providers.map((p) => p.id), chosen);
            selected = selector.value;
            const p = config.providers.find((item) => item.id === selected);
            id.value = p?.id || "";
            base.value = p?.base_url || "";
            env.value = p?.key_env || "";
            enabled.checked = p?.enabled !== false;
            models.value = JSON.stringify(p?.models || {}, null, 2);
            key.value = "";
            ui.status.textContent = "密钥状态：" + (data.keys?.[selected] ? "服务器已有密钥（不可回读）" : "未配置 / 环境变量未设置");
        }
        selector.onchange = () => { try { fill(); } catch (err) { ui.status.textContent = err.message; } };
        button("新增供应商（先禁用）", ui.body, () => {
            try {
                const config = parsed();
                const template = config.providers.find((p) => p.id === selected) || config.providers[0];
                if (!template) throw new Error("请在 JSON 中保留一个有效供应商模板。");
                const ids = new Set(config.providers.map((p) => p.id));
                const added = structuredClone(template);
                do { added.id = "provider_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2); } while (ids.has(added.id));
                added.key_env = "";
                added.enabled = false;
                config.providers.push(added);
                config.fallbacks = [...(config.fallbacks || []), added.id];
                editor.value = JSON.stringify(config, null, 2);
                fill(added.id);
                ui.status.textContent = "已新增并禁用供应商；请配置地址、模型、报价和独立密钥，再启用并保存配置。";
            } catch (err) { ui.status.textContent = err.message; }
        });
        button("删除所选供应商", ui.body, () => {
            try {
                const config = parsed();
                if (config.providers.length <= 1) throw new Error("不能删除最后一个供应商；可取消启用以暂停。");
                config.providers = config.providers.filter((p) => p.id !== selected);
                if (config.primary === selected) config.primary = config.providers[0].id;
                config.fallbacks = (config.fallbacks || []).filter((id) => id !== selected && id !== config.primary);
                editor.value = JSON.stringify(config, null, 2);
                fill(config.primary);
                ui.status.textContent = "已从配置移除，仍需保存。保存后旧凭据仅供历史任务恢复；复用 ID 的新供应商需重新设置密钥。";
            } catch (err) { ui.status.textContent = err.message; }
        });
        button("应用供应商表单到 JSON", ui.body, () => {
            try {
                const config = parsed();
                const p = config.providers.find((item) => item.id === selected);
                if (!p) throw new Error("请先选择配置中存在的供应商。");
                const previous = p.id;
                Object.assign(p, { id: id.value.trim(), base_url: base.value.trim(), key_env: env.value.trim(), enabled: enabled.checked, models: JSON.parse(models.value) });
                if (config.primary === previous) config.primary = p.id;
                config.fallbacks = (config.fallbacks || []).map((value) => value === previous ? p.id : value);
                editor.value = JSON.stringify(config, null, 2);
                fill(p.id);
                ui.status.textContent = "表单已写入 JSON；仍需保存配置。";
            } catch (err) { ui.status.textContent = err.message; }
        });
        button("重新读取 JSON 表单", ui.body, () => {
            try { fill(); } catch (err) { ui.status.textContent = err.message; }
        });
        button("保存配置", ui.body, async () => {
            try {
                const clickedConfig = parsed();
                const saved = await request("/h3-adapter/config", { config: clickedConfig, expected_revision: data.revision });
                for (const id of Object.keys(data.keys)) {
                    if (!clickedConfig.providers.some((p) => p.id === id)) delete data.keys[id];
                }
                data.config = clickedConfig;
                data.revision = saved.revision;
                let refreshError = "";
                try { data.keys = (await request("/h3-adapter/config")).keys; }
                catch (err) { refreshError = " Key 状态刷新失败：" + err.message + "；请重新读取配置。"; }
                if (!ui.isOpen()) return;
                let editWarning = "";
                try { fill(selected); }
                catch { editWarning = " 当前 JSON 编辑无效，尚未保存；请修正后再保存。"; }
                ui.status.textContent = "配置已保存。Key 不在配置中。" + refreshError + editWarning;
            } catch (err) { ui.status.textContent = err.message; }
        });
        let savingKey = false;
        const saveKeyButton = button("保存密钥", ui.body, async () => {
            if (savingKey) return;
            savingKey = true;
            saveKeyButton.disabled = true;
            const providerId = selected;
            const secret = key.value;
            key.value = "";
            try {
                if (!providerId) throw new Error("请先保存并选择供应商。");
                const config = parsed();
                const p = config.providers.find((item) => item.id === providerId);
                if (!p || id.value.trim() !== p.id || base.value.trim() !== p.base_url || env.value.trim() !== (p.key_env || "")) throw new Error("供应商身份表单尚未应用；请先应用到 JSON 并保存配置，再保存密钥。");
                if (JSON.stringify(config) !== JSON.stringify(data.config)) throw new Error("配置 JSON 尚未保存；请先保存配置，再保存密钥。");
                const saved = await request("/h3-adapter/key", { provider_id: providerId, key: secret, expected_revision: data.revision });
                if (!ui.isOpen()) return;
                data.keys[providerId] = saved.has_key;
                if (selected === providerId) ui.status.textContent = secret ? "密钥已保存服务器；输入框已清空。" : "已删除服务器文件中的密钥；环境变量需服务器端另行删除。";
            } catch (err) { if (ui.isOpen() && selected === providerId) ui.status.textContent = err.message; }
            finally { savingKey = false; saveKeyButton.disabled = false; }
        });
        button("本节点使用所选供应商", ui.body, () => {
            if (widget(node, "provider")?.value !== selector.value) setWidget(node, "parameters", "{}");
            setWidget(node, "provider", selector.value);
            ui.status.textContent = "provider = " + selector.value + "；选择 auto 可恢复自动主备。";
        });
        button("本节点恢复 auto", ui.body, () => {
            if (widget(node, "provider")?.value !== "auto") setWidget(node, "parameters", "{}");
            setWidget(node, "provider", "auto");
        });
        fill(widget(node, "provider")?.value);
    } catch (err) { ui.status.textContent = err.message; }
}
async function openPicker(node) {
    const ui = dialog("H3 搜索 / 手动选择模型");
    ui.body.append(element("p", "发现接口只提供实际 ID，不证明 image_edit 或 mask 能力。更换 ID 会清除旧模型能力、报价和参数，须按文档重新声明。保存映射不改变节点 auto / 固定供应商模式；固定供应商请使用供应商管理中的明确选择按钮。没有发现接口时仍可手工填写。"));
    try {
        const data = await request("/h3-adapter/config");
        const config = data.config;
        const provider = element("select");
        provider.setAttribute("aria-label", "模型供应商");
        ui.body.append(provider);
        options(provider, config.providers.map((p) => p.id), widget(node, "provider")?.value === "auto" ? config.primary : widget(node, "provider")?.value);
        const alias = input("逻辑模型别名", ui.body);
        alias.value = widget(node, "model_alias")?.value || "background-edit";
        const search = input("搜索模型", ui.body);
        const list = element("select");
        list.size = 8;
        list.setAttribute("aria-label", "发现的模型列表");
        list.style.width = "100%";
        ui.body.append(list);
        const manual = input("实际模型 ID", ui.body);
        let ids = [];
        let generation = 0;
        const filter = () => options(list, ids.filter((id) => id.toLowerCase().includes(search.value.toLowerCase())), list.value);
        search.oninput = filter;
        list.onchange = () => { manual.value = list.value; };
        const current = () => config.providers.find((p) => p.id === provider.value);
        async function discover() {
            const thisGeneration = ++generation;
            const p = current();
            manual.value = p.models?.[alias.value.trim()]?.id || "";
            ids = Object.values(p.models || {}).map((m) => m.id);
            filter();
            ui.status.textContent = "正在读取模型列表…";
            try {
                const found = await request("/h3-adapter/models", { provider_id: p.id });
                if (thisGeneration !== generation) return;
                ids = [...new Set((found.models || []).filter((id) => typeof id === "string"))];
                filter();
                ui.status.textContent = "来源：" + (found.source === "api" ? "供应商发现 API" : "手动配置") + "；" + (found.warning || "模型能力未由发现结果验证。");
            } catch (err) {
                if (thisGeneration === generation) ui.status.textContent = err.message + " 可手动填写实际 ID，或从配置映射选择。";
            }
        }
        provider.onchange = discover;
        alias.onchange = discover;
        button("刷新模型列表", ui.body, discover);
        button("保存映射并用于本节点", ui.body, async () => {
            try {
                const name = alias.value.trim();
                const id = manual.value.trim();
                const selectedProvider = provider.value;
                if (!name || !id) throw new Error("逻辑别名和实际模型 ID 不能为空。");
                const latest = await request("/h3-adapter/config");
                const p = latest.config.providers.find((item) => item.id === selectedProvider);
                if (!p) throw new Error("供应商已删除；请重新打开模型选择器。");
                const previous = p.models[name];
                const changed = !previous || previous.id !== id;
                p.models[name] = { ...(changed ? { task: "image_edit", supports_mask: false, max_images: 1, price_upper_bound: null, allowed_params: [], defaults: {} } : previous), id };
                await request("/h3-adapter/config", { config: latest.config, expected_revision: latest.revision });
                Object.assign(config, latest.config);
                generation++;
                if (changed || widget(node, "model_alias")?.value !== name) setWidget(node, "parameters", "{}");
                setWidget(node, "model_alias", name);
                if (changed) ui.status.textContent = p.id + " / " + name + " 映射已保存，节点供应商模式保持不变。旧模型能力、报价和默认参数已清除；请在供应商配置 JSON 中按文档重新确认后执行。";
                else ui.close();
            } catch (err) { ui.status.textContent = err.message; }
        });
        await discover();
    } catch (err) { ui.status.textContent = err.message; }
}
function showReport(node, message) {
    let report = Array.isArray(message?.report) ? message.report[0] : message?.report;
    if (report === undefined) return;
    try { if (typeof report === "string") report = JSON.parse(report); } catch { /* report may be plain text */ }
    node.h3ReportText = typeof report === "string" ? report : JSON.stringify(report, null, 2);
    if (node.h3ReportElement) node.h3ReportElement.textContent = node.h3ReportText;
    node.setDirtyCanvas?.(true, true);
}
app.registerExtension({
    name: "h3.adapter",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "H3ImageEdit") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            this.addWidget("button", "H3 供应商 / 密钥", null, () => openManager(this), { serialize: false });
            this.addWidget("button", "H3 搜索 / 选择模型", null, () => openPicker(this), { serialize: false });
            this.h3ReportElement = element("pre", "尚未执行。报告来自实际节点执行，不是云端部署状态。");
            Object.assign(this.h3ReportElement.style, { whiteSpace: "pre-wrap", maxHeight: "220px", overflow: "auto", margin: "6px", fontSize: "12px" });
            this.addDOMWidget?.("h3_report", "h3_report", this.h3ReportElement, { serialize: false, getValue: () => "", setValue: () => {} });
            return result;
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const result = executed?.apply(this, arguments);
            showReport(this, message);
            return result;
        };
    },
});
