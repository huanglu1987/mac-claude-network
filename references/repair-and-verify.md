# 修复和实际验证

## 已确认配置及保留项

2026-10-20 的基线：规则模式，TUN 开启；`🤖 Claude` → `🇺🇸 IPRoyal 固定出口`；该 SOCKS5 节点为 `207.90.214.106:12324`，启用 UDP，`dialer-proxy` 为 `🚀 节点选择`。混合端口从当次 `/configs` 读取，不能硬编码历史 7900；本次飞书修复前后实际均为 7897。节点选择历史为 `🇺🇲 美国 01`。未来用户合法更换中转时，不要因为与历史节点名不同就切回；检查代理链可用、无自循环、出口仍为已确认固定 IP。

当前已确认的三个持久例外：

```yaml
prepend:
  - DOMAIN,stun.l.google.com,🇺🇸 IPRoyal 固定出口
  - AND,((PROCESS-NAME,Claude Helper),(DOMAIN,nexus-websocket-a.intercom.io)),🇺🇸 IPRoyal 固定出口
  - DOMAIN,stun.cloudflare.com,🇺🇸 IPRoyal 固定出口
```

2026-10-22 又批准了两条桌面辅助规则，置于上述三条核心例外之后，详见[修复与边界记录](#桌面-widget-与-hcaptcha-修复及验证边界)：

```yaml
- AND,((PROCESS-NAME,Claude Helper),(DOMAIN,widget.intercom.io)),🇺🇸 IPRoyal 固定出口
- AND,((PROCESS-NAME,Claude Helper),(DOMAIN-SUFFIX,hcaptcha.com)),🇺🇸 IPRoyal 固定出口
```

Claude 主域名/静态资源/登录域名以 baseline.json 为准。原订阅含更广的 Sentry、Statsig、Datadog、Sift、Intercom 和 IP 段规则；保持原状，不把它们升级为新的修复要求。Chrome 的同域 Intercom/hCaptcha 仍走原规则；`api-iam.intercom.io` 不在新增范围，不能因它不走 IPRoyal 而判新增规则失败。

保护 `profiles/Script.js` 的公司域名 DNS、hosts、fake-IP 排除、DIRECT 逻辑。保护 CloudFlare、Google/Gemini、ChatGPT 等其他组的选择和规则。不得把整个 Google、整个 Cloudflare、所有 Intercom 端口或全部 UDP 改道。

Claude Code/MCP 保护路径（只列存在情况/哈希，不展示值）：`~/.claude/`、`~/.claude.json`、`~/Library/Application Support/Claude/claude_desktop_config.json`，以及本次任务明确涉及项目的 `.mcp.json`、`.claude/settings*.json`。不扫描全盘项目，不把运行中会变化的会话文件哈希当网络故障。检查 Code 的代理环境变量时只输出是否设置、无认证信息的主机/端口，不能输出 API key、完整 env、MCP 参数或完整 settings。

## 最小修复流程

1. 运行 `audit`，核实活跃订阅 UID、规则/代理/组/脚本扩展路径。保存其他组选择和非规则配置的比较基线，避免在两个任务中同时操作同一 Clash 状态。
2. `repair` 只补齐或纠正三个持久例外和缺失/被更早规则截获的 Claude 域名。备份目录默认 `~/.local/state/mac-claude-network/backups/<时间>-<随机标识>`，权限 0700；备份可能含凭据，不输出、上传或提交原文。候选运行配置通过本机 `verge-mihomo -t` 后才写持久规则。校验失败不写。
3. 如果固定代理实体存在但 UDP 或 dialer-proxy 偏离，先沿用上述同一私有备份机制备份准确的代理扩展文件，在该**单一节点**上修正字段，保留用户名密码。身份/IP/端口已变时不要强制覆盖；确认是合法换 IP 还是配置故障。绝不从聊天索取密码。
4. 如果 Claude 组遗漏固定节点，先确认现有订阅脚本作用。历史脚本仅把固定节点从其他组移除、加入 Claude 组；针对实际结构做最小修复，不能重写其他用户脚本。`🤖 Claude` 的选择错误时，利用已观察到的原生 UI 选回固定节点，保存并回读；其余策略组保持不变。不能改全局中转选择来掩盖 Claude 组错误。
5. 规则模式/TUN 已关闭时，报告其影响；若用户明确要求恢复这份基线，可备份后用原生 UI 恢复。属于全局网络状态变化，必须验证公司及其他规则/组没有被改写。不能因为浏览器可用就宣称桌面已被接管。
6. 重新激活同一订阅，不能切换订阅或清空缓存。回读 `/configs`、`/proxies`、`/rules`、`/connections`；其他组选择不变，非规则设置不变。API 返回的 normalized rule 名称可能是 `Domain`/`AND`，不能和原 YAML 字符串做天真的相等比较。脚本会分别检查 API 内容和磁盘配置。
7. 仅在修复已授权且旧连接妨碍验证时，可关闭明确修复目标的单条旧连接，让其自动重连。对于已批准的桌面辅助修复，须同时核实 Claude Helper、Claude.app 进程路径、指定 widget/hCaptcha 目标及旧链；不能关闭其他应用或全部连接、强制退出 Claude、清理浏览器或操作登录。只读模式不关闭任何连接。刷新空白页或打开帮助面板仅限实际验证已获授权时，不能发送聊天/客服消息或完成验证码；无新流量时报告未核实，不退出登录来强行触发。
8. 运行 `audit` 并按下节实测。存在失败时只修复有证据的问题；不原样反复重载。修复脚本返回 backup 路径后，可用 `rollback --backup /绝对备份路径` 回退该脚本的规则变更。回滚检查当前文件仍与该次写入哈希相同，若已有后续编辑则拒绝整文件覆盖，改为人工撤销本次规则。回滚也须重新激活订阅并验证。

脚本以外的修复须额外记录其具体文件与前后哈希；不能声称脚本的规则回滚覆盖了这些额外修改。若重载后出现新故障，优先回退本次对应修改，不覆盖后来用户工作。

## 桌面 widget 与 hCaptcha 修复及验证边界

2026-10-22 22:30 开始的局部修复，仅在当前订阅规则扩展新增上述两条 AND 规则。先备份13份网络配置（0700目录、0600副本），候选通过 Mihomo 校验后写入扩展，原生 UI 重新激活同一 WgetCloud 订阅。最终保留原有三条 STUN/nexus 例外优先顺序，其他规则顺序全部相同；生成配置只增加两条 rules，持久扩展只改 prepend，DNS、代理实体、策略组及公司/飞书策略均未变。

| 当次验证 | 结果及边界 |
|---|---|
| widget.intercom.io | 打开帮助面板触发新请求；真实 Claude Helper/Claude.app 连接命中新增 AND 规则，两条样本上传/下载6080/10625和2081/1563字节，均经IPRoyal |
| hCaptcha | 规则已生效；仅关闭3条属于本次目标、仍走美国01的旧桌面连接，返回204。刷新后未出现新hCaptcha连接，实际流量保持待验证；没有触发或完成验证码，也没有退出登录 |
| nexus WebSocket | 原有指定规则继续走IPRoyal，双向有数据 |
| api-iam.intercom.io | 帮助面板新观察到，仍经原ChatGPT组→美国01；未扩大授权范围，保持不变 |
| 固定出口 | 独立终端Claude trace为207.90.214.106、US、TLS1.3；不是桌面已登录响应直接回显的IP |
| 业务连接 | 无认证HEAD：OA192.168.10.13返回200、NC192.168.10.3返回302、邮件EWS10.8.100.101返回401，飞书公开入口返回200；只证明入口连接，不等于登录、邮件收发或完整文档验收 |
| 保留核对 | 最终审计72 PASS；13份配置中仅规则扩展和自动生成运行配置改变，其他字段/文件、策略组、系统/Wi-Fi DNS与Code/MCP保护文件哈希均一致。Mail退出，未发送或重发邮件 |

当次默认审计器只识别旧nexus AND，新增组合位于前方时曾使3项旧规则顺序报告UNVERIFIED；最终调整新增规则位置以保留旧优先级。本次 Skill 更新补充了**仅这两条已批准 AND** 的API规范化识别（包括DomainSuffix），不把任意未知规则猜成可判定。

默认脚本独立输出 `desktop_auxiliary`：持久/生成/实时规则与顺序、已知宽泛声明及当前流量分别判断。`configuration_status=PASS` 不等于流量已验证；`active_test_status=NOT_RUN` 始终保留。只有当前进程名及Claude.app路径均符合、链含固定节点且双向有数据的样本，才能将对应目标 `actual_traffic_status` 标为PASS。缺失API/样本、身份不足或单向数据为UNVERIFIED，已确认桌面样本走非固定链则为FAIL；其他应用样本不充当桌面证据。输出只含基线域名范围与判断，不保存随机子域名、请求路径、凭据或聊天内容。

历史widget通过不填充当前widget，更不能填充hCaptcha；无hCaptcha样本不触发后台探测、修复、重载、清缓存或关闭连接。默认不启动Mail/Connection Doctor，不发送聊天/客服消息、邮件或重发邮件。保留所有DNS、IPv6和公网出口的既有验证边界；不得把域名请求或元数据判据宣称为载荷解密、账号保证或所有第三方流量固定。两条新增规则仅由审计基线使用，现有自动 `repair` 范围保持原样。

证据：[修复与验证报告](/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/Claude桌面辅助连接修复-20261022-223031/修复与验证报告.md)，同目录 `verification-final.json`、`audit-final.json`、`help-panel-connections.json`、`desktop-final-connections.json`、`scoped-old-connections-closed.json`、`business-connection-checks.json`、`rule-scope-checks.json`。网络私有备份路径见该报告，可能含凭据，不复制到Skill或输出。

## Word、Excel 和 Chrome 插件连接观察

仅在用户要求检查插件时使用：先只读核对当前配置和已有 Mihomo 连接元数据，按目标域名、连接开始时间、进程、代理链及双向字节记录，不读取请求载荷、聊天、文档、Cookie 或凭据。若用户愿意配合，可让其关闭其他两个插件面板、分别重新打开一个面板后立即采样；不要发送消息或选择文档内容。旧连接和未变化的流量不能当作新操作样本。短连接可能在采样前结束，无样本应标记未验证；WebKit、Chrome 网络进程可能由多个应用、扩展或标签共用，时间相符只是支持归因的证据，不是唯一归属证明。

2026-10-27（America/New_York）分开观察：Word 单独打开后观察到 `pivot.claude.ai` 连接走 `Claude → IPRoyal 固定出口` 且双向有数据；Excel 重新打开后观察到 `claude.ai`、`pivot.claude.ai` 新连接走相同链路并有双向数据。样本进程均为 `com.apple.WebKit.Networking`，不能独立证明进程属于对应 Office 插件，也不能证明所有辅助请求或远端看到的 IP。

Chrome 面板重新打开后没有捕获新 Claude 连接，已有连接计数未变化，不能确认扩展出口。较早 Chrome `claude.ai`、`api.anthropic.com` 连接选中固定出口且双向有数据，但可能来自其他页面。只读检查发现当时 Chrome 扩展 `fcoeoabgfenejglbffodgkkbkcdhcgfn` 声明 `nativeMessaging`，代码使用 `connectNative`；本机 `com.anthropic.claude_browser_extension` 宿主允许该扩展，类型为 stdio，路径位于 Claude 应用内，相关宿主进程由 Chrome 启动。由此支持本地通信机制和宿主运行，不能证明该时刻有消息交换、具体载荷或所有扩展外网流量的出口。扩展版本、宿主及进程状态会变化，复查应重新取证，不把历史结果升级为当前通过。

Mihomo 代理链反映所见连接的选路，不直接展示每个远端看到的 IP；仅在用户授权的实际出口测试中另行核实，不以终端或其他应用的 trace 代替插件证据。默认 `audit` 不执行插件交互、Native Messaging 通信、外网探测、缓存清理或配置修改，不把本节历史记录写入当前结果。Microsoft 的 Office 服务直连不等同 Claude 主连接直连，也不因此修改其他应用分流。

## DNS 验证与例外

2026-10-20 已确认的公网 DNS 为 `https://1.1.1.1/dns-query#🇺🇸 IPRoyal 固定出口` 和 `https://1.0.0.1/dns-query#🇺🇸 IPRoyal 固定出口`，由既有全局 `profiles/Script.js` 的 `config.dns.nameserver` 赋值持久生成。仅改生成 YAML 不会持久生效。写法依据 [Mihomo DNS 文档](https://wiki.metacubex.one/config/dns/)。这是此用户当前基线，不是所有代理客户端的通用语法。

`audit` 只检查生成文件中的主 DNS、备用/直连及其他域名策略，验证 OA/NC/邮件精确 Wi-Fi DHCP 策略与不固定IP、其他公司私有 DNS 与飞书例外、TUN DNS 劫持和可判定的实时公司 DIRECT 规则，并读取已知持久声明。主 DNS 的 JSON 数组赋值、OA/NC/邮件三个 DHCP 策略键与飞书两个策略键的唯一双引号 JSON 数组声明可静态解析；邮件另核对已知 `const domain`、hosts克隆与 `delete config.hosts[domain]` 声明；出现额外hosts语句或未知形式时不推断已删除。缺少可辨认声明或使用复杂脚本时返回 UNVERIFIED，不能执行任意配置脚本来获得“通过”。本地 `/configs` 不提供上游 DNS 列表时，不能把生成文件或声明哈希当作内核实际 DNS 出口证明。

以下是保留项：

- OA/NC/邮件三个精确主机使用 `["dhcp://en0"]`，仅跟随 Wi-Fi DHCP DNS；业务流量保留 DIRECT。不能扩大到整个公司域名，不永久绑定当次私有或公网 IP。
- 其他公司域名由 `+.ziyondpharma.com` 使用 `192.168.10.40`、`.43`、`.46`，保留 DIRECT、fake-IP 排除、`use-hosts` 和其他已确认 hosts。邮件精确域名不再固定到 `10.8.100.101` 或任一公网 IP；其他公司主机的保护不因此取消。
- 飞书仅 `+.feishu.cn`、`+.feishucdn.com` 使用 `https://dns.alidns.com/dns-query`。只在这些精确策略键与指定上游相符时豁免，不把同一解析器用于主 DNS、备用/直连 DNS 或其他域名也当作豁免；两项缺失或改值均提示偏离。
- `default-nameserver`、`proxy-server-nameserver`、`proxy-server-nameserver-policy` 属于引导/节点解析例外；国内上游可保留。不得要求“全机绝不出现国内 DNS”或对未知 DNS URL 输出原文（可能包含认证信息）。
- 默认审计不发公网/公司 DNS 查询，也不打开检测网站，不刷新系统/Chrome 缓存或强制重载网页。报告的 `actual_test_status=NOT_RUN`、`company_access_status=NOT_TESTED` 必须保留。配置偏离并不等于实际发生泄露。

用户要求实际测试时，在当前 Chrome 使用 `https://ip.net.coffee/dns/` 点击快速或深度测试，记录当次解析器、测试时间和结果。若解析器位于国内，区分普通测试域名、公司内网和飞书业务域名，并结合当前客户端、本地与代理端解析、浏览器安全 DNS 及规则路径定位，不仅凭第三方总分判失败。飞书例外只适用于相应域名，不能拿它解释普通随机测试域名走国内 DNS。DNS 解析器 IP 无须等于 IPRoyal 出口 IP；第三方地区标签也不是物理位置的独立证明。不要上传本地配置、Cookie、会话或代理凭据。

用户已确认 OA/NC 在公司外也能登录，且后续实测证实它们有公网入口。当前改为跟随 Wi-Fi DHCP DNS，复测时分别核对两项精确策略、当前网络下的解析结果、DIRECT 和 HTTP/浏览器登录页；不能仅因在家或无公司 VPN 就断言必须等待公司网络。其他公司私有服务仍需结合当前公司网络/VPN 状态判断。历史公网和私有 IP 都不是永久 hosts 绑定的授权。

历史复测记录：`/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/Mac-DNS修复与验证-20261020.md`。当时环境页从中国电信解析器变为美国 Cloudflare，深度测试显示 26 个美国解析器；公司内网未验收。此记录仅作背景，不能代替未来实测。

### Google解析器来源与判定方法

2026-10-22在公司Wi-Fi上的实际排查，针对Net.Coffee DNS页面同时出现Cloudflare、Google进行独立随机域名对照。结果定位到普通“美国01”业务链带来的代理端解析；不是把Google永久列为安全例外，也不是证明所有Google解析都来自同一节点。节点服务端内部DNS配置未直接读取，未来节点、规则或客户端变化须重新取证。

| 当次对照路径 | 检测站记录的递归解析器 |
|---|---|
| 只调用Mihomo `/dns/query`，不连接测试域名网页 | Cloudflare 2 |
| 终端正常TUN HTTPS，实际走美国01 | Cloudflare 4、Google 3 |
| 不经过Chrome，本地SOCKS主机名模式，实际走美国01 | Cloudflare 4、Google 3 |
| 单次探测走既有IPRoyal，提交域名由出口解析 | Cloudflare 2 |
| 同一IPRoyal链，Mihomo先解析，再提交目标IP | Cloudflare 2 |

固定链先通过Claude trace验证为207.90.214.106、US。两个固定链pixel请求返回403，但TLS证书有效，权威DNS记录已取得；403不是DNS对照失败，也不能判断Claude可用性。浏览器8轮新随机请求实际走美国01，检出Cloudflare 9、Google 19，均被页面标为美国；终端无需Chrome也复现Google，因此Chrome安全DNS不是当次现象的必要原因，不能声称已读取或关闭该开关。

当次读取公开页面源码发现，`getUserIP`请求的是 `https://1.1.1.1/cdn-cgi/trace`；随机图片请求才是 `<probe-id>-<round>.d.ip.net.coffee/pixel.gif`，结果从 `/api/dns/result/<probe-id>` 取回。源码早期注释与实际执行代码不完全一致，应以真实请求和执行分支为准。此前Chrome Helper到1.1.1.1:443走美国01有普通出口检测用途，不能仅凭端点把它判为DoH绕行，也不能据此豁免未来所有同端点连接。

**默认脚本行为：** `dns.resolver_path_observations`只处理本机API已经存在的连接，不发送DNS、HTTPS或随机测试请求，不读取Chrome私有运行时或密码，不执行页面源码。它识别已知解析器端点的53/853/443连接及精确测试后缀中的单层随机域名HTTPS，分别报告FIXED、DIRECT、OTHER_PROXY、UNKNOWN和客户端类别、双向数据。端点观察标为 `RESOLVER_ENDPOINT_PURPOSE_UNVERIFIED`，不凭此确定DoH、递归解析器品牌或泄露；元数据不包含请求路径，不能确认trace还是dns-query。`OBSERVED`只说明取到了匹配样本，`NO_MATCHES_IN_SNAPSHOT`只说明该时点没取到；API不可用报告UNAVAILABLE。归因始终UNVERIFIED、实际对照始终NOT_RUN，不自动把历史结果写成当前通过，也不改变现有业务检查的PASS/FAIL。

只有用户明确要求实际排查来源时，再按证据做有限对照：

1. 保存当前配置/规则/策略组的哈希和脱敏快照；核对主DoH、业务例外、fake-ip及实际代理链。解析器地区、ASN或品牌不能单独确定本机是否直连。
2. 先检查检测页当前公开实现：怎样生成随机域名、取权威记录和查网页出口。浏览器操作用页面UI；不通过evaluate发网络请求，不把下载JS作为本地程序执行，不绕过内部页/安全策略。
3. 每条路径采用独立的新随机关联ID和相同目标后缀，区分“仅解析”与“真正连接网页”。比较Mihomo DNS、本机普通请求、本地SOCKS主机名请求、单次IPRoyal域名/IP对照，并同步取连接链。每条路径先验证路由/出口，不能把手动指定域名/IP当作内核最终目标证据。[curl SOCKS主机名模式说明](https://curl.se/docs/manpage.html#--socks5-hostname)。
4. 单次IPRoyal对照可复用既有认证到内存，但绝不写入命令参数、日志或输出；不能切全局策略、改订阅、关闭现有连接、清缓存或新增监听来完成对照。测试关联ID不是用户登录令牌，不发送本地配置、浏览历史或私有业务数据。Mail保持原状态，不启动或发送/重发邮件。
5. 将新ID的权威结果与对应连接链关联，记录缺失、失败及HTTP/DNS区别。只有“本机解析对照无Google、美国01请求增加Google、固定链对照无Google”等一致证据，才支持当次代理端来源归因；仅有品牌、国家或某一连接端口不足。对照不能完成就保留未核实，不为检测页评分改变网络。
6. 分别回答：是否有相对于IPRoyal的其他代理端解析、是否有本机直连解析的证据、Claude专用链是否出现同类问题；不把三者互相替代。家庭/其他网络未测不能外推。获得足够证据后停止，不重复随机探测。

这次结论是普通代理业务存在相对于IPRoyal的另一条远端解析路径，未观察到国内解析器或Claude专用链同类绕行；不代表全机所有DNS严格经IPRoyal。保留公司DHCP/私有DNS、飞书与引导DNS例外，不能因为出现Google自动删改这些业务策略。

证据：[诊断报告](/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/DNS解析来源只读排查-20261022-210303/诊断报告.md)、同目录 `comparison-summary.json`、`controlled-connections.json`、`fixed-chain-results.json`、`检测页相关源码.txt`、`preservation.json`。该次13份网络配置、规则、策略组、Wi-Fi与系统DNS均未变，默认审计69项通过，未发送或重发邮件；历史数量不代替新审计。

### Claude DNS 路径实测方法与边界

2026-10-22 21:22（America/New_York）公司 Wi-Fi 上，对 Claude 专用路径另做了实际检测。方法用于用户明确要求的有限主动检测；默认 `audit` 不运行以下外网、DNS 或 TLS 探测。

1. 先保存网络文件哈希、实时规则语义、策略组和 Wi-Fi/系统 DNS 快照；保持 OA/NC/邮件的精确 DHCP DNS、其他公司私有 DNS、DIRECT 和飞书加密 DNS 例外。记录 Mail 是否运行，不启动 Mail/Connection Doctor，不发送或重发邮件。只核对配置保留时，不能声称业务已重新验收。
2. 对选定主机 `claude.ai`、`api.anthropic.com`、`claude.com`、`anthropic.auth0.com` 分别经已有本地 Mihomo `/dns/query` 查询 A/AAAA。同时为 `claude.ai`、`anthropic.com` 各生成一次新的 `codex-dns-<随机值>` 子域名，查询 A/AAAA，减少把旧名称缓存当作新查询的可能。新名称的 NXDOMAIN 是有效否定应答，不是业务故障。新名称不能保证递归服务器完全无缓存；需要结合连接证据和独立权威记录。
3. 在限定时间窗口记录已存在的 DoH 端点链及查询前后双向字节变化；上次 4 次随机名称查询均看到 1.1.1.1/1.0.0.1 在 IPRoyal 链上且双向增长。元数据不能解密 DNS 载荷，也可能混入背景请求，不能单凭字节增长或 443 端口作逐查询归因。
4. 对选定真实主机建立新 TLS 连接，使用普通域名、原始 SNI 和默认信任证书校验；按本地源端口关联 Mihomo 实际连接链，不能用 `--resolve` 或手工目标地址代替最终内核证据。可用未认证 HEAD 根路径及 Claude trace 获取连通/出口证据，不发送聊天或调用生成接口。桌面既有连接另取实际元数据；无需启动或登录新会话。
5. 按上节方法，用每条路径独立的新关联 ID 做权威 DNS 记录对照：仅 Mihomo DNS、普通 TUN 网页、既有 IPRoyal 域名解析、同链先解析后提交 IP。对单次固定链先验证 trace 出口；凭据只在内存。不得为探测切策略组、改配置、清缓存、关连接或扩大业务例外。第三方测试域名的权威记录支持该对照路径，不能声称直接读取了 Claude 的权威日志或代理服务端内部设置。
6. 综合配置、实际查询、TLS/桌面连接链、出口及独立权威记录；证据缺失即保留未核实。最后比较前后快照并停止。未观察到绕行仅限所测主机、连接和时段，不覆盖全部软件、未来请求、所有 IPv6 路径或未读取的 Chrome 私有安全 DNS 设置。

当次结果（历史，不自动导入当前审计）：

| 证据 | 结果 |
|---|---|
| Chrome / 终端 Claude trace | 均为 207.90.214.106、US |
| 4 个主机 A/AAAA 加 4 次新随机名称查询 | 共 12 次；随机名称均 NXDOMAIN；解析器连接在固定链上 |
| 4 个新 TLS 连接 | 全部证书校验有效、TLS1.3，连接链包含 IPRoyal；HEAD 状态依次 403/404/200/302，不代表账号或完整业务成功 |
| Claude 连接快照 | 共 8 个样本，含桌面 API TCP 和 claude.ai UDP，未见非固定链 |
| 权威记录对照 | Mihomo DNS、IPRoyal 域名/IP 两种路径均 Cloudflare 2；普通美国01 TUN 为 Cloudflare 4 + Google 3 |
| 配置保留 | 13 份网络文件、实时规则语义、策略组及系统/Wi-Fi DNS 未变；Mail 未运行 |

据此判为 `NO_BYPASS_OBSERVED_IN_TESTED_CLAUDE_PATHS`。Google 在普通美国01对照出现，未在固定链对照出现，不能拿普通检测页的 Google 直接判定 Claude 绕行。固定链测试站 pixel HTTP403 但 TLS 和权威记录有效；403 不等于 Claude 功能不可用。真实主机返回 AAAA 时，Wi-Fi IPv6 仍 Off；AAAA 应答不等于发生 IPv6 连接或泄露。

默认脚本新增 `dns.claude_path_observations`：按已批准域名的精确/后缀边界识别现有业务连接，仅输出基线域名范围，不输出任意子域名、请求 URL、进程路径或认证信息。分别计数 FIXED、DIRECT、OTHER_PROXY、UNKNOWN；报告传输、双向数据及 IPv6 目标观察。Intercom 和 STUN 仍由现有独立检查负责。缺少 API/样本分别为 UNAVAILABLE/NO_MATCHES_IN_SNAPSHOT，均不能表示无绕行。即使全为 FIXED，`dns_path_status` 仍 UNVERIFIED，`actual_test_status`、`tls_test_status`、`authoritative_comparison_status` 仍 NOT_RUN；连接路径不替代实际 DNS 归因。非固定样本提示调查，不自动诊断 DNS 泄露或改变既有业务检查。历史结果保存在引用记录；默认脚本不会读旧实测来冒充当前通过。

证据：[实测报告](/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/Claude-DNS路径实测-20261022-211933/检测报告.md)，同目录 `actual-summary.json`、`claude-dns-and-tls.json`、`live-connections.json`、`resolver-comparison.json`、`resolver-geo.json`、`verification.json`。当次默认配置审计 68 PASS，仅代表配置及该次现有连接检查；与主动 DNS 实测分开记录。

#### 2026-10-22 21:49 复测记录

公司 Wi-Fi、Wi-Fi IPv6 Off；使用更新后的 Skill 和新的随机名称/独立关联 ID，未复用首轮探测结果。4 个主机仍为 `claude.ai`、`api.anthropic.com`、`claude.com`、`anthropic.auth0.com`。

| 复测证据 | 结果 |
|---|---|
| DNS 查询 | 共 12 次 A/AAAA；4 次新随机名称查询均 NXDOMAIN，且均观察到固定链解析器连接双向字节增长 |
| 新 TLS / 连接样本 | 4 个新 TLS 均证书有效、TLS1.3、真实链包含 IPRoyal；共捕获 9 个 Claude 连接，非固定链 0，含桌面 API TCP 和 claude.ai UDP |
| 浏览器 / 终端 trace | 均为 207.90.214.106、US |
| 独立权威记录 | Mihomo DNS、IPRoyal 域名/IP 两种路径均 Cloudflare 2；普通美国01 TUN 为 Cloudflare 3 + Google 3 |
| 保留核对 | 13 份网络文件、实时规则语义、策略组及系统/Wi-Fi DNS 均一致；默认审计 69 PASS；Mail 未运行，未发送或重发邮件 |

结论仍为 `NO_BYPASS_OBSERVED_IN_TESTED_CLAUDE_PATHS`，仅限这轮主机、样本和时段。4 个新 TLS 的 HEAD 状态仍为 403/404/200/302，固定链 pixel 为 403；不作为账号业务验收。未读取 Chrome 私有安全 DNS、Claude 权威日志或代理服务端内部配置；字节增长不是载荷解密，AAAA 不等于实际 IPv6 连接。OA、NC、邮件、飞书及公司其他内网只检查配置保留，未重做业务验收。品牌数量是当轮观测值，不能设为以后必须相同的基线，也不合并首轮 8 个与复测 9 个连接作为独立总样本。

证据：[复测报告](/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/Claude-DNS路径复测-20261022-214931/检测报告.md)，同目录 `actual-summary.json`、`claude-dns-and-tls.json`、`live-connections.json`、`controlled-connections.json`、`resolver-comparison.json`、`resolver-geo.json`、`verification.json`、`audit.json`、`Chrome-Claude-trace.txt`。历史实测与默认脚本的 NOT_RUN/UNVERIFIED 状态继续分开保存；本记录不改变任何业务检查、默认只读行为或上文验证边界。

#### 2026-10-22 22:03 再检测记录

公司 Wi-Fi、Wi-Fi IPv6 Off。对同一组 4 主机重新查询 A/AAAA，并使用新随机名称及各路径独立的新关联 ID；未复用此前样本。

| 本轮证据 | 结果 |
|---|---|
| DNS / TLS | 12 次 A/AAAA，4 次随机名称均 NXDOMAIN，且均观察到至少一个固定链解析器连接双向字节增长；4 个新 TLS 均证书有效、TLS1.3、实际链包含 IPRoyal |
| 实际连接 | 8 个 Claude 域名连接，非固定链 0；逐项样本包含桌面 Claude Helper 的 API TCP、Chrome 的 claude.ai UDP，不能把本轮 Chrome UDP 写成桌面 App UDP |
| Chrome / 终端 trace | 均为 207.90.214.106、US |
| 独立权威记录 | Mihomo DNS、IPRoyal 域名/IP 两种路径均 Cloudflare 2；普通美国01 TUN 为 Cloudflare 3 + Google 3 |
| 保留核对 | 13 份网络文件、实时规则语义、策略组、系统/Wi-Fi DNS 及 Skill 文件均未变；默认审计 68 PASS；Mail 未运行，未发送或重发邮件 |

本轮结论为 `NO_BYPASS_OBSERVED_IN_TESTED_CLAUDE_PATHS`。保留上述全部边界：历史样本不累加或自动变为当前通过；品牌数量不设为基线；端点和字节增量不是逐查询载荷归因；未读取 Chrome 私有安全 DNS、Claude 权威日志或代理服务端内部配置。AAAA 不等于 IPv6 连接，HEAD 403/404/200/302 及固定链 pixel 403 不作账号业务判据。本轮 OA、NC、邮件、飞书及其他公司内网只核对配置保留，未重新验收业务。

证据：[再检测报告](/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/Claude-DNS路径再检测-20261022-220259/检测报告.md)，同目录 `actual-summary.json`、`claude-dns-and-tls.json`、`live-connections.json`、`controlled-connections.json`、`resolver-comparison.json`、`resolver-geo.json`、`verification.json`、`audit.json`、`Chrome-Claude-trace.txt`。具体进程/传输以 `verification.json` 的本轮逐项连接为准，不沿用旧轮描述。默认脚本及所有业务检查不变，实际测试状态仍 NOT_RUN、DNS 归因仍 UNVERIFIED；本历史记录不触发探测或修复。

### 飞书 DNS 例外及故障复查

2026-10-20 用户报告飞书文档变慢后，已授权备份并添加以下持久策略；不是让所有国内网站都使用国内 DNS：

```yaml
nameserver-policy:
  +.feishu.cn:
    - https://dns.alidns.com/dns-query
  +.feishucdn.com:
    - https://dns.alidns.com/dns-query
```

源为既有 `profiles/Script.js` 的 `config.dns["nameserver-policy"]` 对象，与公司策略并存；默认 Cloudflare DoH/IPRoyal、公司私有 DNS、其他路由与策略组不变。检测脚本检查生成配置的两项值和上述已知持久声明，不自动新增、删除或改写策略，也不自动进行飞书请求。`dns.feishu_exception.status` 描述生成配置是否属于批准范围，不证明持久源已生效或文档可打开；结合独立检查项和 `actual_test_status` 阅读。

当时当前 DNS 把飞书主机解析到 `98.96.*`、`155.102.*` 等地址，国内 DNS 为同一主机返回国内 CDN。对比 HEAD 请求从约 1.05–2.14 秒降为修复后约 0.082–0.156 秒，属于单次请求样本，不是完整文档加载时间。Chrome 中既有文档标题、目录和正文已加载；客户端的新连接走 DIRECT 且有响应，但未单独验收其具体文档。Claude 网页出口仍为 `207.90.214.106`，公司内网访问未测试。

历史证据：`/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/飞书DNS只读排查-20261020/修复与验证报告.md`；私有网络备份 `work/feishu-dns-backup-20261020-111701` 位于该任务工作目录。备份可能含凭据，不输出原文。

用户要求实际诊断时，先看相关主机的新连接和当前 DNS 回答，再按需比较国内解析。`/dns/query` 为实际查询，会产生解析请求；默认 audit 不调用它。若用 `curl --resolve` 比较，明确它只影响当次请求，不修改 hosts，且仍可能经过 TUN；根路径 HEAD 的 404 只表示该路径不存在，不能据此判断业务接口故障。验证具体文档需只读打开其标题/目录/正文，不能以 DNS 或 HTTP 检查替代，也不发送聊天、编辑文档或上传日志。

### OA/NC 跟随 Wi-Fi DNS 及缓存处理

#### NC DHCP DNS 端口冲突与恢复记录

2026-10-26，公司 Wi-Fi 下 NC 正常域名解析为公网 `221.228.243.90`，访问未获得有效页面；绑定当时 Wi-Fi 地址以 TCP 查询三台公司 DHCP DNS，均返回内网 `192.168.10.3`，临时直接访问该地址的 NC 入口返回 302。Clash DNS 连续返回旧公网答案（TTL 1），系统也返回公网答案。未经接口绑定的 DNS 查询可能被 TUN 拦截，不能据此判定公司 DNS 返回了公网地址。

用户授权备份和修复后，先备份生成配置、持久脚本、订阅信息及当前规则扩展，备份目录为 `/Users/huanglu/Documents/Codex/2026-10-16/new-chat/work/nc-dns-backup-zqhs5js3`；可能含凭据，不展示内容。确认 Mail 已退出后，调用 Mihomo `POST /cache/dns/flush` 清除的是**全部 DNS 缓存**，不是仅 NC；随后 NC、OA、邮件查询均失败，错误为 `listen udp4 0.0.0.0:68: bind: address already in use`。错误确认 DHCP 解析器绑定端口失败，未确认端口占用进程，也不能断言旧缓存是唯一根因。勿把失败后的影响省略为单域名故障。尝试 API 重载时因服务的安全路径限制返回 400，未绕过限制。

用户保持 Mail 退出并重新激活当前订阅后，三项 DHCP DNS 查询恢复：NC `192.168.10.3`、OA `192.168.10.13`、邮件 `10.8.100.101`；系统解析一致。正常域名 NC 返回 302、OA 返回 200，邮件 EWS 未认证 HEAD 返回 401 且证书验证通过；未登录 NC/OA、未发送或重发邮件。Claude trace 为 `207.90.214.106`、US，飞书公开入口 HTTP 200；不代表所有后台连接或飞书文档均已验收。默认审计配置 PASS，三份持久文件与备份一致；生成配置前三条规则顺序改变但内容保留，策略组选择一致。此结果是当次证据，不代表以后 DHCP DNS 始终可用，也未证明下次切网正常。

今后诊断先比较 Clash、系统和绑定当前 Wi-Fi 的公司 DNS 答案，结合 NC 入口及 OA/邮件受影响范围。`audit` 默认不主动查询、清缓存、重载或检测 UDP 68 占用；需要实际排障时，明确区分缓存、运行时解析和内网连通性。缓存刷新或重载前，若用户禁止发送邮件，应先确认 Mail 已退出或由用户置离线，避免自动重试。不可因历史内网地址有效而固定 hosts 或自动替换 DHCP 上游；配置 PASS、旧记录、DNS 应答及 HTTP 状态不等于业务登录成功。

2026-10-22 用户授权仅修复 OA/NC：公司 Wi-Fi 的 DHCP DNS 为 `192.168.10.40`，公司三台 DNS 均返回 OA `192.168.10.13`、NC `192.168.10.3`；旧公网入口在公司网络下不通，绑定物理 Wi-Fi 仍不通。以下为当前批准基线，取代下一节的旧公网策略：

| 精确策略键 | 当前批准上游 |
|---|---|
| `oa.ziyondpharma.com` | `["dhcp://en0"]` |
| `erp.ziyondpharma.com` | `["dhcp://en0"]` |

只改变既有 `profiles/Script.js` 和生成 `clash-verge.yaml` 中上述两个值。未永久写入私有 IP，未更改系统 DNS、Wi-Fi、IPv6、路由或策略组。JavaScript 语法、Mihomo 配置校验通过；现有本地控制器加载返回204。当次邮件精确公网 DNS、公司其他私有 DNS、DIRECT、fake-IP 排除、Claude 和飞书保留；邮件后续另经授权改为 DHCP，见邮件当前记录。

`dhcp://en0` 使用该接口 DHCP 下发的 DNS，不等于手工设置的系统 DNS；它只适用于当前已确认的 Wi-Fi 接口。家庭/外网切换及其他接口尚未实测，不能承诺所有缓存立即随网络刷新。脚本分别检查两个精确值、持久声明、OA/NC hosts 缺席及公司 DIRECT；不会将任意 `dhcp://`、其他接口、公司后缀或普通公网策略一并豁免。

当次验证与缓存处理按层分开记录：

1. 内核 A 查询先已改为 OA `192.168.10.13`、NC `192.168.10.3`，AAAA无记录，但 macOS 仍缓存旧公网 `221.131.102.242`。仅 `dscacheutil -flushcache` 未清除；非交互 sudo 因需要密码而未执行。用户自行运行 `sudo /usr/bin/killall -HUP mDNSResponder` 并确认后，系统 `getaddrinfo` 才返回正确私有地址。该命令只作已授权排障记录，不由默认审计运行；管理员授权必须用户本机完成，不索取密码。不要反复重设系统 DNS 代替定位缓存。
2. 系统缓存更新后，通过正常域名、无 `--resolve`/hosts 覆盖，OA HTTP200（约0.024秒）、NC HTTP302（约0.024秒），目标分别为上述私有 IP。NC Chrome 登录页已显示；HTTP成功与浏览器成功分别验收。
3. OA Chrome 仍空白，用户手动打开 `chrome://net-internals/#dns` 点击 **Clear host cache** 并确认。自动工具访问该内部页曾被 URL 安全策略拒绝，没有改用原始协议或其他接口绕过；需要该操作时由用户自行完成，不清除 Cookie、历史或登录数据。
4. OA 原始控制台仍显示私有网络访问阻止：`The request client is not a secure context and the resource is in more-private address space local`。临时私有 IP 对照可显示登录页；随后在确认目标标签页后，通过 Chrome 原生 **View → Force Reload This Page**，正常域名的 OA 登录页完整显示。旧页面缓存或网络地址空间状态参与故障是据此作出的推断，不能把所有空白页归为 DNS。参考 [Chrome 私有网络访问说明](https://developer.chrome.com/blog/private-network-access-preflight)。不能关闭浏览器安全检查、CORS、证书验证或批量删除会话来修复。
5. 未输入凭据或点击登录，没有验收业务操作；临时 IP 对照不是永久入口。后续实际排障依次比较内核查询、系统答案与浏览器错误/页面，再按证据处理具体缓存层，默认审计不执行这些步骤。

当次 Claude 浏览器与终端 trace 均为 `207.90.214.106`、US；飞书入口302、CDN根路径404且响应迅速，404不代表具体文档故障。公司其他 DNS/规则配置保留，不表示全部内网业务已验收。当次邮件公网及经 Clash 的临时内网对照均有 TLS 超时；后续诊断确认临时内网对照被内核重新解析回公网，不能据此认定内网服务器不可达。邮件后续修复见下一节当前记录；此处不把历史超时保留为当前结论。

证据：[修复与验证报告](/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/OA-NC随WiFi-DNS修复-20261022/修复与验证报告.md)，同目录的 `after-system-cache-refresh.json`、`after-chrome-cache-clear-http.json`、`browser-final.json`、`authorized-scope-checks.json` 及邮件复核记录。私有网络备份为任务目录 `work/oa-nc-wifi-dns-backup-20261022-201927`，可能含凭据，不分享原文。该次13份配置中仅两份/两个策略值变化，16项保留检查通过。

这些是历史实测，不填入本次默认审计结果。`dns.company_wifi_dns.status=EXEMPT` 仅指生成策略符合范围；同时查看持久源、hosts与DIRECT检查。`actual_test_status`、`cache_test_status`、`browser_test_status` 均保留 `NOT_RUN`，公司访问仍为 `NOT_TESTED`。旧审计因未接纳 DHCP 例外而出现的三项 FAIL 应通过更新准确基线解决，不能删除检查、放宽普通公网策略或恢复旧公网值。

### OA/NC 公网 DNS 例外及验证记录（历史）

本节仅为历史；2026-10-22 已由上一节 Wi-Fi DHCP 基线替代，不据此恢复旧公网策略。

2026-10-20 用户确认修改 DNS 前在公司外也能登录 OA/NC，授权仅修复两个精确主机。原公司后缀策略把它们发往当时不可达的私有 DNS，两项查询均在 5 秒超时；公网 DNS 有可达的入口。已在既有 `profiles/Script.js` 的 `nameserver-policy` 中持久增加以下两项，并同步加载生成配置：

| 精确策略键 | 2026-10-20 当时批准上游 |
|---|---|
| `oa.ziyondpharma.com` | `https://1.1.1.1/dns-query#🇺🇸 IPRoyal 固定出口`、`https://1.0.0.1/dns-query#🇺🇸 IPRoyal 固定出口` |
| `erp.ziyondpharma.com` | 同上两项 |

以下为2026-10-20当次历史记录；邮件旧hosts于2026-10-21另经授权移除，见下一节。OA/NC修复当时只改变两台业务主机的解析；实际 OA/NC HTTP 连接仍走 DIRECT。公司后缀三台私有 DNS、其他公司主机、邮件 hosts、fake-IP 排除、全部路由和策略组，以及 Claude、飞书设置原样保留。脚本分别校验生成策略、其他公司策略范围和持久声明，不能把公司后缀存在当作两项公网例外仍存在的证据。`dns.company_public_dns.status` 仅描述生成策略；必须同时查看持久声明检查项。默认只读审计的该项 `actual_test_status=NOT_RUN` 不引用历史结果冒充本次实测。

当次验证完成于 2026-10-20 11:39（America/New_York）：

- 本机 DNS 对两域名均返回 `221.131.102.242`，约 0.712 秒。公网阿里 DNS 当时返回 `221.228.243.90`，两组地址的相关端口均可达；这些是当次答案，不是固定 IP 基线。
- 使用正常域名请求，OA 的 8081 端口返回 HTTP 200（约 0.150 秒）；NC 的 8092 端口返回 302 同域登录跳转（约 0.149 秒）。实时连接记录为 DIRECT，目的地址与当前 DNS 一致且有双向数据。
- 当前 Chrome 的原 OA 和 NC 网址均实际加载登录页，未填写或发送凭据、未点击登录。账号登录、业务操作及公司网络内回环可达性尚未验收。
- Claude Chrome trace 仍为 `207.90.214.106`、US、HTTP/3。修复前后全部策略组选择与规则结构一致；当时旧版 audit 为 62 项 PASS，这个历史数量不代替更新后检查。

历史证据：[修复与验证报告](/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/OA-NC外网访问排查-20261020/修复与验证报告.md)。私有网络备份为该任务 `work/oa-nc-public-dns-backup-20261020-113750`，可能含凭据，不输出原文。今后只有实际访问再次失败且用户授权修复时才考虑修改；调用本 Skill、更新检测脚本或出现配置偏离均不授权改网络。

### 邮件跟随 Wi-Fi DHCP DNS 及缓存处理

2026-10-22 公司网络诊断确认：邮件精确公网DNS返回 `61.160.91.22`，该入口在公司Wi-Fi下连接超时；公司三台DNS均返回 `10.8.100.101`，绑定物理en0、保留原域名SNI及证书验证时，EWS无认证HEAD可返回401。Clash日志显示，临时 `--resolve` 内网IP的请求仍可能被识别为邮件域名后重新连接公网入口，因此不能把该对照的超时当作内网服务器或TUN/TLS引擎故障的证明。

用户授权后，私有备份13份配置，仅把 `profiles/Script.js` 和生成 `clash-verge.yaml` 中 `email.ziyondpharma.com` 的一个值改为 `["dhcp://en0"]`。JavaScript/Mihomo校验退出0，本地控制器加载204。保留DIRECT、不写hosts、不修改系统DNS、Wi-Fi、IPv6、Claude、OA/NC、飞书或其他内网。当前邮件基线已取代下一节旧公网策略，不因历史私有地址可用而永久固定IP。接口仅为en0，家庭/外网及其他接口切换尚未验证。

缓存与连接分层验证如下：

| 层次 | 当次结果 |
|---|---|
| 内核DNS | 修改后A为10.8.100.101，AAAA无记录；不等于系统缓存已同步 |
| 初次正常域名请求 | 无--resolve/物理接口覆盖，EWS返回401、证书有效；系统及TUN目标元数据仍显示旧公网，不能单凭该元数据证明物理出站目标 |
| 系统缓存处理 | `dscacheutil -flushcache` 退出0仍未清除旧地址；用户在本机自行运行 `sudo /usr/bin/killall -HUP mDNSResponder` 并确认。默认审计不会运行这些命令；管理员密码不进入聊天或日志 |
| 最终系统解析与正常请求 | 20:50:40（America/New_York）系统答案和curl目标均为10.8.100.101；正常域名EWS约28毫秒返回401，证书验证0、TLS1.2 |
| 最终实时链路 | 邮件连接destinationIP为10.8.100.101、chains仅DIRECT，命中公司域名规则且有双向数据 |
| 认证和收发 | 未认证、未发送/重发邮件；401只证明认证入口可达，不代表账号或投递验收 |

修复前Mail已在运行，界面工具未能操作；用户自行确认完全退出，进程检查证实后才加载修复，验证结束仍未运行。以后明确授权修复但禁止发送时，先确认Mail退出或由用户置离线，避免恢复网络触发原待发邮件自动重试；不能自动打开Mail或Connection Doctor来做连接验证，也不删除待发邮件或改账号。由用户自行决定何时恢复客户端。

当次OA返回200、NC返回302，Claude终端出口仍207.90.214.106、US，飞书入口302且证书正常；未验收完整文档、业务登录或实际收发。运行配置语义仅邮件DNS一个值变化，全部实时规则、策略组及系统网络设置保留，9项核对通过。旧Skill当时67 PASS/3 FAIL对应新DHCP例外尚未入基线；本次更新后应按新基线检查，不能删除普通公网保护或公司其他DNS范围检查来消除偏离。

当前脚本同时检查三个精确DHCP策略、已知持久声明、静态hosts缺席及公司DIRECT；邮件保留独立的 `dns_mail_wifi_upstreams`、`dns_mail_wifi_persistent_source` 与旧映射删除声明检查。`dns.mail_dns.status`只描述生成策略，必须结合持久源、hosts、DIRECT检查阅读；`actual_test_status`、`cache_test_status`、`connection_test_status`均为NOT_RUN。默认审计不发DNS/TLS请求、不刷新缓存、不重载、不启动Mail；上述历史28毫秒/401不填入本次审计结果。

证据：[只读诊断](/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/公司邮件连接只读排查-20261022/诊断报告.md)、[修复与验证报告](/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/邮件随WiFi-DNS修复-20261022/修复与验证报告.md)，后者同目录 `after-cache-refresh.json`、`preservation-and-audit.json`、`final-preservation.json`。网络私有备份为任务目录 `work/mail-wifi-dns-backup-20261022-204719`，可能含凭据，不分享原文。

### 邮件公网 DNS 例外及验证记录（历史）

本节为历史；邮件当前已改为上一节Wi-Fi DHCP DNS，不恢复下述公网基线或旧hosts。

2026-10-21 用户在家使用 Mac Mail 发送 Exchange 邮件失败。旧 `email.ziyondpharma.com → 10.8.100.101` 映射在当前网络上导致 TLS 失败；两家公网 DNS 均返回 `61.160.91.22`，该入口经证书校验可达。用户授权备份后仅移除旧映射、给该精确主机增加公网加密 DNS，并明确禁止发送或重发邮件。

2026-10-21当时基线：`email.ziyondpharma.com` 精确策略使用原两台 Cloudflare DoH，均指定 `🇺🇸 IPRoyal 固定出口`；邮件业务流量仍为 DIRECT。`company_hosts` 已移除旧邮件映射要求，`company_unpinned_hosts` 单独要求该精确主机不存在静态 hosts，并加入公司 DIRECT 实际规则检查。脚本还静态读取已知持久删除声明，不执行 JavaScript。原公司后缀私有 DNS、其他 hosts、fake-IP 排除、use-hosts、OA/NC、飞书和 Claude 设置保留。

当次修复于2026-10-21约10:00（America/New_York）验证：

| 项目 | 当次结果与范围 |
|---|---|
| 本机DNS | 邮件域名返回61.160.91.22；这是当次答案，不是永久hosts或新的固定出口基线 |
| 正常域名EWS | `https://email.ziyondpharma.com/EWS/Exchange.asmx` 的无凭据HEAD返回401，证书验证结果0，目标61.160.91.22，总耗时约0.207秒；不是用resolve覆盖DNS的结果 |
| 认证与收发 | 401证明未认证请求已到达认证入口；未验证账号登录、客户端收发、邮件投递 |
| 保留核对 | OA返回200、NC返回302；Claude仅终端trace仍为207.90.214.106、US。13份配置仅授权的两文件/两字段变化，全部策略组和规则结构不变；飞书正文和公司内网未重新验收 |
| 排队邮件 | 当时发现1封待发邮件，在失败提示中选择Try Later后退出Mail；未点击重发或发送测试邮件，未删除/改写原邮件内容，没有重新打开Mail或Connection Doctor |

2026-10-22 公司网络复核：邮件仍解析至 `61.160.91.22`，未认证 EWS TLS 超时；绑定物理 Wi-Fi 到同一公网地址也超时，临时解析到公司 DNS 返回的 `10.8.100.101` 对照仍超时。此处是当次未修复状态；后续已定位重新解析问题并完成上述DHCP修复，不把这次临时内网超时当作服务器不可达的证据，也不沿用为当前故障结论。未打开 Mail 或 Connection Doctor，未发送或重发邮件。

当前默认 `audit` 仅检查配置与本机API GET；邮件DHCP策略、持久声明、旧映射缺席和DIRECT均单独检查，历史401不会被填成本次实测成功。`dns.company_unpinned_hosts.status` 仅描述生成配置的精确映射是否缺席；同时查看持久源检查项。`actual_test_status=NOT_RUN` 与 `company_access_status=NOT_TESTED` 保留。

用户以后明确要求实际邮件连接测试时，先确认待发邮件状态；打开Mail或恢复连接可能触发原排队邮件自动重试。只读检测、Skill更新和网络连接测试不授权发送、重发、删除邮件或更改账号。无认证HEAD可验证DNS/TLS/EWS可达性，不能代替已登录客户端验收。不能只因历史私有映射曾修好另一网络，就恢复它；公司网络中的访问仍需当场验证。

历史证据：[修复与验证报告](/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/邮件连接修复-20261021/修复与验证报告.md)。私有网络备份为该任务 `work/mail-public-dns-backup-20261021-095841`，可能含凭据，不输出原文。此前报告中“已安装Skill尚未同步”的描述是当时状态；该时点的公网例外已被后续DHCP基线取代；保留此记录仅辅助追溯。

## 实际验证（不发送聊天消息）

配置通过、规则命中、实际出口是三个不同层次。默认按下列顺序验证，及时报告缺口：

| 项目 | 操作与判据 |
|---|---|
| Claude 网页 | 在用户当前使用的 Chrome 打开 `https://claude.ai/cdn-cgi/trace`；只读取 ip、loc、http 字段。ip 应为基线的 `207.90.214.106`，loc=US。其他新 IP 不能静默接受为新基线。配合对应时间的连接记录核对链。终端通过当前混合端口得到同 IP 只证明那次终端请求，不能替代 Chrome。 |
| Claude Desktop | 查看实时 `api.anthropic.com` 等核心域名连接，进程为 Claude/Claude Helper，路由链含固定节点且有双向字节；应用未运行或无新连接时标记未核实，不能借其他进程的 claude.com MCP 流量替代。需要启动应用时用原生 UI；重新登录由用户完成。 |
| Claude Intercom | 对指定主机观察 Claude Helper 新连接，AND 规则、固定节点、双向字节。Chrome 同域仍走原组是保留范围成功，不是失败。若新版本使用新进程/主机，只报告实际证据，不自动把规则放宽到所有进程或后缀。 |
| Google STUN | 打开 `https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/`，使用唯一服务 `stun:stun.l.google.com:19302`，点击 Gather candidates。不授权麦克风摄像头。有效 srflx 候选应为固定 IP；结合 Mihomo UDP 记录，上传和下载均 >0。 |
| Cloudflare STUN | 同一官方示例通过 UI 移除其他服务，只添加 `stun:stun.cloudflare.com:3478`，Gather；使用同样判据，结束后 Restore/Reset to defaults。 |
| 保留核对 | 与备份比较：只修改已批准的文件/字段和规则，其他策略组选择不变。Code/MCP 文件只报告存在/变化情况，不能复制其内容。运行中的自然变更不得自动恢复。 |

701 host lookup 警告与有效 IPv4 srflx 可同时出现：记录二者，不能以警告否定已收到的 IPv4 响应，也不能以 IPv4 成功宣称 IPv6 全覆盖。只有 host/mDNS 候选、日志里仅出现域名、UDP 发出却无响应，均不足以证明 STUN 成功。API 没记录短连接时，重新触发一次有意义的测试并及时取样，不做无限轮询。

使用 CUA 时，第一调用遵守工具入口文档。浏览器 evaluate 仅做只读 DOM 检查，不用它创建 PeerConnection 或请求网络；用网页 UI 触发测试。不要采集 BrowserLeaks 完整 SDP，因为含 ICE 密码；截取候选表或读取指定字段即可。不能通过 osascript/AppleScript 绕过 UI 工具。

若无可用浏览器控制工具，给用户确切的测试步骤，静态部分照常完成；标记实际出口未核实。第三方网络风险页若未走 Claude 规则，其 HTTP 出口和 WebRTC IP 不一致不必然是家庭公网泄露；以实际候选和路由链判断，不为了“全绿”改变语言时区或启用指纹浏览器。

## 语言、时区与定位记录

以下为 2026-10-20 用户明确授权的个人设置记录，不是使用 Claude 的强制条件。单独调用网络检测或更新 Skill 不授权重做这些变更。

### Mac 已完成与未完成项

| 项目 | 调整前 | 2026-10-20 已确认状态 |
|---|---|---|
| 系统首选语言 | 简体中文第一，英语（美国）第二 | 英语（美国）第一，简体中文第二 |
| 时区 | 上海 / China Standard Time | `America/New_York`；页面为纽约市、北美东部夏令时间，`/etc/localtime` 只读回读同一 IANA 区域 |
| 自动定位时区 | 开启 | 关闭，以保留手动选择的纽约时区 |
| 自动校时 | 开启，Apple `time.apple.com.` | 保持开启，时间源不变 |
| Chrome 网页首选语言 | 本次未读取确认 | 工具未修改或核实；内部设置页受浏览器安全策略拦截，未绕过 |
| 页面 `Intl locale` | 用户后来报告 `zh-CN` | 未有重启后的新测试，不写成 `en-US` 或“已修复” |
| 重启 | 语言修改前各应用运行中 | 已选择暂不重启；部分应用的新语言尚待重启生效 |

保留简体中文、原地区美国、公历、华氏度、美制、星期日起始、原日期/数字格式、中文拼音列表排序、实况文本、原应用语言覆盖列表、24 小时制及锁屏时间格式。主要语言切换曾自动把列表排序改为“通用”，已恢复原中文拼音排序；以后不因语言修改顺带改地区、键盘或格式。

变更与原值截图记录：`/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/Mac语言与时区调整-20261020/调整记录.md`。这些是历史证据，不是每次调用时的实时状态。

### 固定 IP 的定位核实

查询对象必须是 Claude trace / 订单已确认的同一个固定 IP `207.90.214.106`，不能用普通检测页、美国 01 或其他 IPv6 出口的城市来推断该固定 IP 的时区。

| 查询日期 | 来源 | 返回城市 | 返回时区 |
|---|---|---|---|
| 2026-10-20 | [IPinfo](https://ipinfo.io/207.90.214.106) | Ashburn, Virginia, United States | `America/New_York` |
| 2026-10-20 | [IPWHOIS](https://ipwho.is/207.90.214.106) | Washington, District of Columbia, United States | `America/New_York`，当时 EDT / UTC−4 |

两家当次 ASN 均返回 AS7029 / Windstream Communications LLC。城市略有差异，但均属于美国东部时区；所以本次保留纽约时区有依据，不应根据其他出口的“Los Angeles / AS21859 Zenlayer”标签改为洛杉矶。`America/New_York` 是区域时区名，不要求城市恰好是纽约，也不意味着永久 UTC−4；冬季会按区域规则使用 UTC−5。若以后确认同一 IP 的数据库结果变化或互相冲突，报告来源、日期和不确定性，再决定是否需要调整，不能自动换时区或更新固定出口基线。数据库定位不证明服务器精确物理地址。

### 只读复查方法与停止条件

1. 只有当前任务问到环境偏好时，读取系统语言顺序、地区、列表排序、自动时区与校时状态；时区可只读回读 `/etc/localtime`。不要为只读检查触发系统解锁、保存或重启。
2. 分开记录 Chrome 网页首选语言、Chrome 界面语言、检测页面实际显示的 Intl locale 与时区。系统语言已经保存不等于 Chrome 已重新加载新环境；英语网页优先也不单独证明 Intl 已为英语。
3. `Intl locale` 是页面国际化格式使用的语言区域标记；若页面调用时明确传入语言，它未必代表浏览器默认值。检测实现不明时标记未知。`zh-CN` 本身不是 IP、DNS 或 WebRTC 泄露证据，也不能独立推出 Claude 封禁风险。
4. 如需实际观察，按可用工具读取页面显示的字段或由用户提供截图。CUA evaluate 限只读 DOM，不用它执行任意运行时探针；没有已显示字段就保留未验证，不冒充实测。浏览器安全策略拒绝内部页时，不改用其他入口、原始协议或配置文件写入绕过。
5. 完全退出/重开 Chrome、重启 Mac 只在用户明确要求或授权时进行；保存未提交工作，尊重浏览器会话。可说明 Apple 提醒部分应用需要重启，而不是把重启设为只读检测必经动作。
6. 语言、时区和定位结果单独列为观察项，不加入 DNS/固定出口的强制修复判据。公司 DNS、DIRECT、网络路由、登录会话和其他应用保持原样。

参考：[Apple 系统语言与重启说明](https://support.apple.com/guide/mac-help/change-the-system-language-mh26684/mac)、[MDN Intl locale 字段说明](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat/resolvedOptions)、[MaxMind 定位精度说明](https://support.maxmind.com/knowledge-base/articles/maxmind-geolocation-accuracy)。

## 历史证据（仅辅助定位）

原验证报告：`/Users/huanglu/Documents/Codex/2026-10-16/new-chat/outputs/Google-STUN与Claude-Intercom固定出口验证-20261020.md`。2026-10-20 当时 Google/Cloudflare 均取得固定 IP 的 srflx；Claude Intercom 命中 AND；Chrome 同域保留美国 01。后续检测必须新取证，不把该历史结果当当前状态。
