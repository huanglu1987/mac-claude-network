# Claude 桌面旧账号偏好清理记录

本机历史记录，日期为 2026-10-23，时间均为 `America/New_York`（当日 UTC−4）。用于回答本次清理范围及后续只读保留检查，不是通用账号清理流程，也不是再次修改配置的授权。下列 `<old_account>`、`<old_org>` 为脱敏标记，不是可直接用于删除的字面键名。

## 已授权并完成的范围

两轮清理均仅修改 `/Users/huanglu/Library/Application Support/Claude/claude_desktop_config.json`，删除下列 4 个旧账号成员，保留整个映射及其他账号成员；第二轮在用户授权退出 Claude、确认相关进程结束并重新备份后执行：

| 精确成员模式 | 当次用途判定 |
|---|---|
| `preferences.bypassPermissionsOptInByAccount[<old_account>]` | 跳过权限确认的选择记录 |
| `preferences.bypassPermissionsGateByAccount[<old_account>]` | 对应功能的可用状态缓存 |
| `preferences.coworkModelAutoFallbackByAccount[<old_account>]` | 模型自动回退偏好 |
| `preferences.epitaxyPrefs["epitaxy-auto-default-notice-seen.<old_account>"]` | 提示已读标记 |

这 4 项当次均为布尔值，属于偏好或功能缓存，不能当作登录令牌。不是删除 `preferences`、整个账号映射、整个 `epitaxyPrefs` 或任何钥匙串项。旧账号的 Code 界面分组缓存在清理前已由运行中的客户端自行移除，未纳入本次写入。

`/Users/huanglu/Library/Application Support/Claude/config.json` 未改动，以下旧组织扩展安全策略缓存按原值保留：

- `dxt:allowlistEnabled:<old_org>`
- `dxt:allowlistLastUpdated:<old_org>`
- `dxt:allowlistCache:<old_org>`

当前新账号、其他偏好、MCP、项目配置、本地记忆和网络设置均在保留范围。组织策略不是旧账号授权凭据；不要为清理个人偏好删除安全策略缓存。历史中的账号标识不能代替今后的当前账号核实。

## 备份与证据

### 首轮：客户端运行时的历史备份

私有目录：`/Users/huanglu/Documents/Codex/2026-10-16/new-chat/work/claude-desktop-old-preferences-cleanup-20261023-073617/`。仅用于解释首轮清理及后来写回的经过，不再作为最近一轮复查基线。

| 文件 | 内容与作用 |
|---|---|
| `claude_desktop_config.json.before` | 修改前目标文件的完整备份 |
| `config.json.before` | 修改前账号及组织策略配置的完整备份 |
| `manifest.json` | 目标、4 个脱敏成员路径、修改前与计划修改后哈希、`protected_before` 文件哈希清单 |
| `verification.json` | 07:36:48 写入后的本地验证 |
| `verification-final.json` | 07:37:18 的延迟复读，包含 15 秒观察等待 |

目录权限为 0700，文件为 0600。完整备份属于私有配置，不能输出全文、上传或将其中秘密复制到报告。只输出脱敏字段路径、状态、数量和哈希。只读复查不需要访问钥匙串、启动应用或读取秘密值。

首轮目标清理后 SHA-256：`0bd78cd7bc4e1606609bb622def884f5680ef8f10ffc9f26bd329f9fa94bb44b`，后来已被运行中的客户端写回，不能当作最新目标哈希。

### 最近一轮：退出后重新备份

当前只读复查使用的私有目录：`/Users/huanglu/Documents/Codex/2026-10-16/new-chat/work/claude-desktop-old-preferences-after-quit-20261023-080134/`。

| 文件 | 内容与作用 |
|---|---|
| `claude_desktop_config.json.before` | 相关进程结束后，重新读取的最新目标文件完整备份 |
| `config.json.before` | 退出后当前账号及组织策略配置的完整备份 |
| `manifest.json` | 本轮 4 个成员范围、前后哈希、169 个非目标保护文件的新哈希及退出方式 |
| `verification.json` | 08:01:34 写入后的本地验证 |
| `verification-final.json` | 08:02:13 延迟复读，包含 20 秒观察等待及进程复核 |

新目录权限为 0700，文件为 0600。第二轮目标清理后 SHA-256：`bfb328f2042fc60e69e5d89471e69b374f2f4b64471b6093e1c0d9fd411f614d`。应以新目录中的实际记录核对，不把任何历史哈希当作永不变化的配置要求，也不自动恢复整份备份。

## 已完成的验证与边界

### 首轮清理与写回经过

- 初次验证：JSON 有效；与备份相比恰好删除 4 个成员，其他文本字节不变，文件权限保留；当前账号及 3 个组织策略值不变，`config.json` 字节不变。
- 保护验证：`manifest.json` 中 169 个非目标受保护文件均与当次写入前哈希相同，覆盖 MCP、项目配置、本地记忆、Claude Code 用户状态及网络设置。目标文件另与精确清理结果比较，不能把 169 解释为全部本机文件。
- 延迟复读：4 个成员仍缺席，目标哈希保持上述值，169 个文件无变化或缺失。
- 07:38:04 再次只读复查：上述结果继续成立；该轮结果来自本对话工具输出，未另写复查报告。
- 07:42:42 更新 Skill 期间再次只读核对：4 个旧账号成员全部重新出现；当前新账号仍与清理时一致且不是旧账号，3 个旧组织策略缓存值不变。两份桌面配置哈希与 Skill 更新前快照不同，其余 168 个纳入比较的文件未变。该轮结果来自本对话工具输出，未另写报告或执行再次清理。这与运行中客户端写回内存偏好的现象相符，但未独立追踪实际写入进程；不能报告为持续清理成功，也不能据此推断旧账号授权被恢复。
- Claude 在执行前已运行（当次主进程 PID 76756）；任务未启动或重启它。07:37、07:38 未见写回只描述当时的观察窗口，07:42 已见重新出现，不能沿用较早结果推断当前状态。
- 后续只读追查：主进程日志 `main.log` 的 07:41:49“Config file written”与目标文件修改时间吻合；恢复的 4 项值与首轮清理前一致，另外仅新增 `keepAwakeEnabled`、改变 `sidebarMode`。本地程序代码显示配置按进程缓存，偏好更新从内存对象合并后保存整份配置。证据高度支持当前进程在保存其他偏好时带回旧成员；未抓取内存堆或独立跟踪写入系统调用，不据此推断旧授权被恢复。

### 第二轮退出后清理与末次验证

- 用户明确授权后，通过 Claude 菜单“退出 Claude”正常退出主进程及桌面 Helper。残留的 Chrome 原生桥接进程 `/Applications/Claude.app/Contents/Helpers/chrome-native-host` 收到 SIGTERM 后结束；未退出 Chrome、未使用 SIGKILL，也未重新启动 Claude。
- 备份前、写入前及末次验证均未发现相关 Claude 进程。备份以退出后最新文件为准，保护哈希也在退出后重新采集，不把退出时客户端正常保存的状态误判为清理造成的改动。
- 08:01:34：JSON 有效，恰好删除同一 4 个旧账号成员，其他文本字节及文件权限保留；新账号标识未变，`config.json` 字节未变，旧组织 3 个策略缓存值未变，169 个非目标受保护文件未变。
- 08:02:13：延迟复读通过，4 项仍缺席，目标哈希与本轮精确清理结果一致；相关进程为空，169 个文件无变化或缺失，新账号及旧组织策略值保持。备份目录 0700、文件 0600。
- 末次通过只覆盖 Claude 退出后的有限观察窗口；没有重新启动来验证下一次启动是否再生成偏好，也没有验证客户端内存状态。未来运行时若有合法偏好变化，应重新归因，不用本轮哈希强行覆盖。
- 两轮均未发起网络请求、MCP 功能调用、在线授权或邮件测试；文件保留不等于在线功能或授权有效性已验证，也不证明不会再次封禁。

### 更新 Skill 时的后续只读观察

08:19:26 本次文档更新的本地复核发现：4 项仍缺席，目标文件仍匹配第二轮清理后的哈希；Claude 新主进程 PID 3832 的启动时间为 08:17:28。本次文档更新没有启动或退出 Claude，也未发送请求，启动来源未在本次任务中追查。`config.json` 已与第二轮 08:02 的快照不同，其余 168 个非目标保护文件未变；该差异本次未作字段归因。这不推翻 08:02 进程为空的历史结果，也不构成完整的启动后、账号或 MCP 在线功能验证。后续只读复查应区分第二轮清理基线和客户端后来合法写入的状态，不自动恢复旧 `config.json`。

## 后续只读复查方法

1. 默认读取最近一轮退出后备份 `claude-desktop-old-preferences-after-quit-20261023-080134/` 的 `manifest.json`、`verification.json`、`verification-final.json` 及两份 `.before` 文件，首轮记录仅用于追查写回历史。在本机内存中确认目标和旧账号归属，不输出账号完整标识或配置全文。旧账号参考来自工作目录 `/Users/huanglu/Documents/Codex/2026-10-16/new-chat` 下保留的 `work/claude-code-login-metadata-20261023-030246/claude.json.before` 的 `oauthAccount`，也属于私有备份。不能把当前 `lastKnownAccountUuid` 当作待删除的旧账号。
2. 解析当前两份桌面 JSON，逐一检查 4 个旧账号成员缺席；与目标备份仅删除这 4 项后的结构比较，再与 `verification.json.after_sha256` 比较字节哈希。结构相同但哈希不同应区分格式差异，其他字段变化须逐项归因。
3. 将当前 `lastKnownAccountUuid` 与 `config.json.before` 比较，核对旧组织 3 个策略值以及 `config.json` 哈希；按 `manifest.json.protected_before` 检查 169 个文件，明确报告缺失和变化，不自动恢复。客户端正在运行或用户已切换账号时，差异本身不能证明清理造成故障，需只读核对已有日志及用户确认的操作。
4. 仅只读列出现有相关进程，不为了复查启动 Claude。若发现写回，报告具体成员与当次证据，不重复删除、不关闭应用、不重载代理。任何再次清理、退出或重启须有与当前操作相符的授权；本历史记录不延续一次性的退出与清理授权。

默认不写报告；仅在用户要求时将脱敏结果保存到指定位置。不要运行 `check_claude.py audit`，它虽是只读检测，仍会请求本地 Mihomo API。本记录不改动现有 Claude 出口、DNS、WebRTC、OA/NC、邮件、飞书或公司内网检查及其验证边界。
