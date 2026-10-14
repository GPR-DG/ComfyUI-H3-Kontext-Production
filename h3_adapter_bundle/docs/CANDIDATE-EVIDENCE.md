# Candidate source evidence

Research only; no adapter implementation or upstream install/import/test/server run.
Collected 2026-10-10 Asia/Shanghai; exact UTC retrieval time is in candidate-manifest.json. Sources cloned from public upstream GitHub with core.autocrlf=false.

## Conclusion before implementation

None of these three is a drop-in implementation for configuration-driven arbitrary providers, model discovery, primary + three backups, durable duplicate-call prevention or ambiguous-POST safety.

1. **Best mask/image reference: Mask-External-Edit.** Native MASK input, crop/paste helpers and local mock examples; actual MIT LICENSE. Network dispatcher/default URLs are vendor-specific, so not reusable unchanged.
2. **Best generic HTTP/node reference: HttpRequestNodes.** MIT, configurable URL/headers/body; no image-edit registry. Exception retry is unsafe to copy unchanged for billable non-idempotent POSTs.
3. **Do not copy UniAPI without license clarification.** README MIT link is broken: pinned tree has no LICENSE, GitHub API license is null. Fixed async task schema also prevents arbitrary protocol support.

Inference: a smaller configured transport/protocol profile adapter is preferable to wholesale reuse; retain ComfyUI native image/mask/node contracts and implement durable request-state handling separately. HTTPX/SQLite alone are not a complete adapter.

## Immutable sources

| Repository | Fixed commit | Last author commit | History | Tracked files | License |
|---|---|---|---:|---:|---|
| [Mask-External-Edit](https://github.com/wuhu290/ComfyUI-Mask-External-Edit) | ef38e815c004c3ad68b5c486c1ffe518183aad00 | 2026-06-05T09:49:50+08:00 | 15 | 10 | LICENSE, MIT, 2026 Mask External Edit contributors |
| [UniAPI](https://github.com/xiaojuzi2024/ComfyUI-UniAPI) | 9fad71b7f08a6fd71216ef0562b048e5526d7179 | 2026-05-13T17:30:20+08:00 | 4 | 3 | No LICENSE; README says MIT |
| [HttpRequestNodes](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes) | fdd4827090dcc02d900c0e60338fcc06cb7b0bac | 2026-06-23T17:12:35+08:00 | 46 | 39 | LICENSE.txt, MIT, 2025 felixszeto |

| File | SHA-256 |
|---|---|
| Mask/nodes.py | cc7af71106e191fb1011a14156e4bc1f049dc48dacd46fdcc5eeb24e0a519f78 |
| Mask/LICENSE | 72f16d4136774e50eb2c48042fed8d4ec364816b6aa480c3f3d89d57a0b66fd5 |
| UniAPI/uni_api_node.py | a736933ae9fe9ac690275cea16b512a39f4470e15fb8b0728bdc6d2388f6ead1 |
| HTTP/rest_api_node.py | 3654d5b685bbf47d10a4cdb8c13dfd7f3c362d19aaf5c407bd651f2827a508e0 |
| HTTP/media_form_post_node.py | 2a9c68cef29f55fbf4a98060ba4c9bfa8bd0e965da0a6b2eb6f208678a00f097 |
| HTTP/LICENSE.txt | f7ed83ba051cc809ffe5464c2089997166ca54dc7738152d79c4f0bcb8e66282 |

Artifacts: candidate-manifest.json (all tracked hashes/paths/sizes); candidate-github-metadata.json (public API metadata/releases); candidate-source-evidence/ (numbered sources); candidate-licenses/ (untouched MIT copies); candidates/ (unmodified upstream checkouts). No upstream code was integrated into an adapter.

## Capability matrix

| Capability | Mask | UniAPI | HTTP |
|---|---|---|---|
| Custom endpoint | Versioned/full image-edit endpoint or custom_http URL | Base URL + fixed /v1 paths | Full target URL |
| Credential | Key or env name, Bearer | Direct key, Bearer | Caller-built headers |
| Model | OpenAI/OpenWond string; custom_http omits model | String | Caller-built JSON/form field |
| IMAGE | First batch element | Four IMAGE ports, first elements | IMAGE batch |
| MASK | Native mask/grow/crop/alpha/paste | None | None |
| Async | None | Fixed task schema | Requests only |
| Discovery/failover/journal | None | None | Same URL retry only |

## Mask-External-Edit: filename and line evidence

All citations use the fixed commit above.
- [nodes.py:422-456](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/nodes.py#L422-L456): IMAGE/MASK inputs, fixed provider menu and final image/crop/mask/status outputs.
- [13-38](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/nodes.py#L13-L38): first batch item only, image alpha converted away.
- [41-103](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/nodes.py#L41-L103), [383-407](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/nodes.py#L383-L407), [481-502](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/nodes.py#L481-L502): polarity heuristic, bbox/padding/downsize and feathered paste-back.
- [134-139](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/nodes.py#L134-L139): inverse-alpha RGBA edit mask.
- [202-282](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/nodes.py#L202-L282): key/env resolution; custom multipart image+mask+prompt+task; OpenAI-style profile adds model/n.
- [351-366](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/nodes.py#L351-L366): hardcoded vendor defaults; root URL gets /images/edits without /v1.
- [506-563](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/nodes.py#L506-L563): single route; error raises/returns original, not failover.
- [142-190](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/nodes.py#L142-L190): image bytes/base64/URL decoder. Returned URLs downloaded without explicit origin/redirect/size policy; up to 1000 response-body characters enter errors.
- [example_openai_mock_server.py:1-44](https://github.com/wuhu290/ComfyUI-Mask-External-Edit/blob/ef38e815c004c3ad68b5c486c1ffe518183aad00/example_openai_mock_server.py#L1-L44): local mock, not assertion suite; uses cgi.FieldStorage.
- No tests/CI; Python >=3.10 metadata; requests/Pillow minimum versions. MIT copyright/license must be retained if substantial code copied.

## UniAPI: filename and line evidence

- [uni_api_node.py:64-103](https://github.com/xiaojuzi2024/ComfyUI-UniAPI/blob/9fad71b7f08a6fd71216ef0562b048e5526d7179/uni_api_node.py#L64-L103): empty URL/model, direct key, IMAGE1-4, no MASK, timeout 900 seconds.
- [137-219](https://github.com/xiaojuzi2024/ComfyUI-UniAPI/blob/9fad71b7f08a6fd71216ef0562b048e5526d7179/uni_api_node.py#L137-L219): fixed /v1/images paths and async=true; base already ending /v1 duplicates that prefix; image files share field name image.
- [224-295](https://github.com/xiaojuzi2024/ComfyUI-UniAPI/blob/9fad71b7f08a6fd71216ef0562b048e5526d7179/uni_api_node.py#L224-L295): HTTP 200 only; 60 x 10-second sleep plus up to 900 seconds per GET, so not a hard ten-minute deadline. No failover/journal.
- [328-429](https://github.com/xiaojuzi2024/ComfyUI-UniAPI/blob/9fad71b7f08a6fd71216ef0562b048e5526d7179/uni_api_node.py#L328-L429): b64_json/URL, PIL verify in main handlers; URL downloads lack explicit trust/redirect/size policy; errors can output colored placeholders.
- [433-496](https://github.com/xiaojuzi2024/ComfyUI-UniAPI/blob/9fad71b7f08a6fd71216ef0562b048e5526d7179/uni_api_node.py#L433-L496): task resume reads nested actual_data then line 462 iterates outer result.data. Static inference: documented completed nested task shape can be reported incomplete; not executed.
- Pinned tree is only README.md/__init__.py/uni_api_node.py. README MIT hyperlink targets absent LICENSE; API license null. No copy clearance.
- No tests/CI/dependency manifest; four commits, no published release.

## HttpRequestNodes: filename and line evidence

- [media_form_post_node.py:17-55](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes/blob/fdd4827090dcc02d900c0e60338fcc06cb7b0bac/media_form_post_node.py#L17-L55), [104-119](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes/blob/fdd4827090dcc02d900c0e60338fcc06cb7b0bac/media_form_post_node.py#L104-L119): URL/image field/form/header configurable; IMAGE batch multipart; no MASK or separate mask part; timeout 300; generic outputs.
- [rest_api_node.py:39-109](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes/blob/fdd4827090dcc02d900c0e60338fcc06cb7b0bac/rest_api_node.py#L39-L109): same-URL request method/retry settings; no request timeout; max_retry=0 with status condition becomes sys.maxsize. Default non-2xx retry flag false unless explicit max_retry without conditions (README broader).
- [111-141](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes/blob/fdd4827090dcc02d900c0e60338fcc06cb7b0bac/rest_api_node.py#L111-L141): all request exceptions retry regardless of method/transmission stage, no idempotency/journal; cannot distinguish definitely-unsent/may-have-billed.
- [form_post_node.py:33-71](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes/blob/fdd4827090dcc02d900c0e60338fcc06cb7b0bac/form_post_node.py#L33-L71): no image POST timeout.
- [binary_post_node.py:63-87](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes/blob/fdd4827090dcc02d900c0e60338fcc06cb7b0bac/binary_post_node.py#L63-L87): timeout 300, exception retries; returns HTTP failures without status retry.
- [test_nodes.py:9-11](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes/blob/fdd4827090dcc02d900c0e60338fcc06cb7b0bac/test_nodes.py#L9-L11), [44-67](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes/blob/fdd4827090dcc02d900c0e60338fcc06cb7b0bac/test_nodes.py#L44-L67): manual audio smoke uses author-local file, LAN endpoint/sample token, writes /tmp; not hermetic/image-edit tests; not run.
- [.github/workflows/publish_action.yml:1-20](https://github.com/ahkimkoo/ComfyUI-HttpRequestNodes/blob/fdd4827090dcc02d900c0e60338fcc06cb7b0bac/.github/workflows/publish_action.yml#L1-L20): publish-only CI. pyproject.toml:5 points to LICENSE but actual file is LICENSE.txt.
- MIT copyright felixszeto retained in fork. Whole plugin imports unrelated audio/video converters, adding avoidable breadth/dependencies.

## Maintenance, tests and security limits

Public GitHub API: all main, archived=false, open_issues_count=0; last pushes UTC Mask 2026-06-05 01:49:53, UniAPI 2026-05-13 09:30:23, HTTP 2026-06-23 09:12:41. Releases endpoints return [] for all (normalized empty-array wrapper in saved JSON). Stars/forks Mask 1/0, UniAPI 6/1, HTTP 1/1, not quality scores.

Source/call-path inspection found no model discovery, cross-provider fallback, journal, keyring, idempotency or explicit redirect policy. No explicit TLS-verification disabling or dynamic exec/eval/subprocess in examined Python. Requests defaults retain TLS verification; absence of suspicious calls is not a security audit. No provider calls/secrets. Failure/resume findings are static inferences, not runtime claims.
