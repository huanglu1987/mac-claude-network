---
name: mac-claude-network
description: 只读检测这台 Mac 的 Claude 固定出口、Clash Verge DNS、公司与飞书 DNS 例外及 STUN/Intercom 路由；仅在明确授权后修复，保留 Claude Code、MCP 和其他配置。不用于手机配置或账号清理。
---

# Mac Claude 网络检测与修复

先告知用户使用本 Skill。默认简体中文。此 Skill 是用户现有配置的维护工具，不是无人值守后台任务。

## 模式与边界

- “检测、是否符合、先不要修改”：只读运行 `audit`，再按需要验证实际出口，不能运行修复、重新选择策略组、重载或关闭连接。
- “检测并修复、修复不符合项”：先审计，告知具体改动范围，备份后执行已授权的局部修复，无须逐条重新索取同一授权。
- 单纯引用 Skill 不代表授权更改。生成 Skill 或基线不代表对当前网络执行修复。
- 保护 Claude Code、MCP、记忆、浏览器档案、登录会话、系统语言时区、DNS、公司 DIRECT 规则和其他策略组。不能用清空账号数据、指纹伪装或把所有流量切到 IPRoyal 来“修复”。
- 用户明确要求“纯本地、不要发送任何请求”时，不运行下文会访问本地 Mihomo API 的 `audit`，仅进行文件读取、JSON 解析和哈希比较；未执行的网络及功能检查保持未验证。

要求及历史值见 [references/baseline.json](references/baseline.json)。它不含凭据。IP、端口和节点名是 2026-10-20 用户已确认的个人基线；IP 变更或新订阅须根据用户新确认的信息更新，不能从第三方评分推断新要求，也不能自动购买或续费。

## 先运行可重复检查

脚本需要已有的 Python 3 和 PyYAML；缺依赖时报告，复用已安装解释器，不能为了检查自动更改全局 Python。

```bash
python3 ~/.codex/skills/mac-claude-network/scripts/check_claude.py audit
```

省略模式参数也默认执行 `audit`。它只读磁盘配置、本地 Mihomo API 和本机语言/接口/路由状态，不发外网或公司内网探测请求，不执行配置脚本、不重载、不关闭连接，不刷新系统或 Chrome 缓存、不强制重载网页，不输出秘密。仅指定 `--output /绝对路径/report.json` 时写入脱敏报告；退出码 0 为配置检查通过、2 为存在偏离或未核实项、1 为无法执行。没有相关新连接时必须保留“待实际验证”，不能把静态通过写成整体验证成功。默认不启动 Mail、Connection Doctor 或收发测试，也不发送或重发邮件。

### 本地环境观察与显式报告比较

报告版本 2 新增 `system_observations`，不参与原有 `configuration_status` 判定，不扩展修复范围：

- `language`：只读系统 `AppleLanguages`、`AppleLocale` 及 Claude 单独的 `AppleLanguages`。缺少单独偏好为 `NOT_SET`，读取失败为 `UNVERIFIED`；不能据此确认运行中客户端或 Chrome 的实际语言。浏览器 `Intl` 保持 `NOT_RUN`。
- `timezone`：读取 `/etc/localtime` 对应 IANA 区域并计算当日 UTC 偏移，按夏令时自然变化，不固定为 UTC−4。读取失败保留未知；不解锁系统、不校时、不查询定位。
- `ipv6`：只读接口 UP/RUNNING 标志及各类 IPv6 地址数量、活动硬件服务配置模式、IPv4/IPv6 默认路由接口，以及生成/内核公开的代理 IPv6 字段。报告不含完整接口地址、MAC、SSID 或网关地址。`live_ipv6=null` 表示接口未提供该字段，不能推断关闭。UP、RUNNING、有全局地址或存在默认路由均不证明实际业务正在绕行；link-local、loopback 地址也不等于公网泄露。未知状态不冒充关闭，`actual_ipv6_path_status=NOT_RUN`；现有连接里的 IPv6 目标观察仍单独保留。

`report_metadata` 包含审计起止 UTC 时间、检测版本/脚本哈希、基线哈希及未执行外网探测的范围；`configuration_fingerprints` 仅报告生成配置和当前规则扩展哈希。哈希变化不代表恶意修改，不能自动恢复运行中应用的自然变化。

默认仅输出当次 JSON，`report_comparison.status=NOT_REQUESTED`，不建立历史目录、不启用定时任务。用户要求保存或比较时才显式指定路径，例如：

```bash
python3 ~/.codex/skills/mac-claude-network/scripts/check_claude.py audit --output /已有目录/current.json
python3 ~/.codex/skills/mac-claude-network/scripts/check_claude.py audit --compare /已有目录/previous.json --output /已有目录/current.json
```

`--compare` 仅限 `audit`，比较输入和输出必须不同。它将新审计与指定旧报告的检查状态、已知观察字段、配置及受保护文件哈希比较，不回显旧报告任意内容。`FULL` 仅表示报告版本、订阅和基线相同且所需比较字段齐全；旧版或缺项为 `PARTIAL`，未知版本为 `UNSUPPORTED_VERSION`。重复名称的检查比较各状态数量，不声称逐条归因。差异不触发重载、清理、账号判断或任何修复；时间戳不会作为配置变化。旧报告的出口、DNS、STUN 结果绝不填入当前检测，`actual_exit_comparison_status=NOT_RUN`。实际出口仍须另按既有流程取得当次证据。

脚本从 `profiles.yaml` 当前 UID 动态找扩展文件，不假定历史文件 ID。核对活跃内核、固定节点身份、UDP、代理链、Claude 组、首个可判定域名匹配、持久 STUN/Intercom 规则；列出 Code/MCP 配置存在情况和不含内容的哈希。`PROCESS-NAME,Claude Helper` 限定指定 Intercom 主机及已批准的 hCaptcha 后缀，不改为所有应用的域名规则。

DNS 检查使用已确认的个人基线：除已批准业务例外外，普通公网查询通过固定出口访问加密 DNS；检查备用/直连/其他域名策略是否旁路，并保留公司私有 DNS、DIRECT、hosts 和 fake-IP 排除。2026-10-22 更新基线：OA/NC/邮件仅 `oa.ziyondpharma.com`、`erp.ziyondpharma.com`、`email.ziyondpharma.com` 三个精确键使用 `["dhcp://en0"]`，跟随 Wi-Fi 接口的 DHCP DNS，业务流量仍为 DIRECT，不固定内外网 IP。分别检查生成策略、已知持久声明及 OA/NC/邮件静态 hosts 缺席；缺失、改值或扩展到其他公司主机均提示偏离，其他公司域名仍保留私有 DNS。此例外不能用于普通公网、主 DNS、备用或直连 DNS。邮件不再要求保留旧 `10.8.100.101` 映射；检查精确邮件 hosts 缺席及已知持久删除声明，不能恢复私有映射或把当次公网 IP 固定进 hosts。飞书例外仅为 `+.feishu.cn`、`+.feishucdn.com` 使用 `https://dns.alidns.com/dns-query`，逐项校验域名、上游及已知持久声明，缺失或改变也提示偏离；不得把例外扩展到所有国内域名、Claude、备用或直连 DNS。

已知持久脚本仅做声明读取与哈希，不执行 JavaScript。`default-nameserver` 与代理节点解析等引导例外可继续使用国内上游，不能据此单独判为普通查询泄露。`dns.feishu_exception.status=EXEMPT`、`dns.company_wifi_dns.status=EXEMPT` 只说明生成配置符合批准范围；`dns.actual_test_status=NOT_RUN`、`dns.feishu_exception.actual_test_status=NOT_RUN`、`dns.mail_dns.actual_test_status=NOT_RUN`、`dns.company_unpinned_hosts.actual_test_status=NOT_RUN` 与 `company_access_status=NOT_TESTED` 均不能写成实际测试通过。`dns.company_wifi_dns` 的 `actual_test_status`、`cache_test_status`、`browser_test_status` 均为 `NOT_RUN`，不代表缓存已更新、切网成功或登录页已加载。当前 OA/NC 策略、缓存分层处理与当次验证见 [OA/NC 跟随 Wi-Fi DNS](references/repair-and-verify.md#oanc-跟随-wi-fi-dns-及缓存处理)；旧公网策略仅保留为历史记录。邮件独立检查为 `dns_mail_wifi_upstreams`、`dns_mail_wifi_persistent_source`；`dns.mail_dns` 的缓存与连接测试状态也保持 `NOT_RUN`。当前邮件修复、缓存处理与验证边界见 [邮件跟随 Wi-Fi DNS](references/repair-and-verify.md#邮件跟随-wi-fi-dhcp-dns-及缓存处理)。旧公网邮件策略仅为历史；即使没有公网公司例外，其他公司域名的私有 DNS 范围检查也必须继续执行。默认不启动 Mail、Connection Doctor 或邮件发送测试，避免待发邮件自动重试。实际检测及业务例外解释见 [DNS 验证与例外](references/repair-and-verify.md#dns-验证与例外)。

DNS解析器品牌与解析路径须分开判断。2026-10-22受控对照将额外Google解析定位到普通“美国01”业务链带来的远端解析；不能据此断言Claude固定链绕行或本机向国内运营商泄露。默认脚本新增 `dns.resolver_path_observations`，只分类现有连接的端点、代理链与双向流量，不发随机域名请求：`actual_comparison_status=NOT_RUN`、`resolver_origin_status=UNVERIFIED`。`1.1.1.1:443`可能是检测页查询出口的普通HTTPS请求，不能凭端口判为DoH；未看到连接也不能判定无泄露。历史证据、实际对照方法和停止边界见 [Google解析器来源判定](references/repair-and-verify.md#google解析器来源与判定方法)。这些观察不放宽主DNS或业务例外，不自动修改任何策略。

2026-10-26 NC 故障表明：DHCP DNS 配置通过不保证运行时正常。默认报告 `dns.company_wifi_dns.dhcp_runtime_status` 和 `udp68_conflict_status` 为 `NOT_RUN`，不查询、清除缓存或假定端口占用来源。需要排障时，区分 Clash、系统与绑定当前 Wi-Fi 的公司 DNS 答案；全局 DNS 缓存清除会影响 OA 和邮件，需结合 Mail 待发状态与具体授权处理。原因和当次恢复见 [NC DHCP DNS 端口冲突记录](references/repair-and-verify.md#nc-dhcp-dns-端口冲突与恢复记录)。

API socket 优先检测 `/var/run/clash-verge-service/users/<uid>/verge-mihomo.sock`，再检测运行文件声明的 Unix socket。controller secret 只从本地配置读取到内存；不能打印、放到命令行参数或写入报告。API 不可达属于未核实，不应靠开放远程 controller 来解决。

### 桌面 widget 与 hCaptcha 的独立检查

2026-10-22 已授权添加 `Claude Helper` 与精确 `widget.intercom.io`、后缀 `hcaptcha.com` 的两条 AND 规则，放在原有 STUN/nexus 例外之后；其他应用及 `api-iam.intercom.io` 原路径保留。修复时 widget 新连接已通过，hCaptcha 刷新后无新连接、实际流量待验证。详见 [桌面辅助连接修复记录](references/repair-and-verify.md#桌面-widget-与-hcaptcha-修复及验证边界)。这些状态是历史记录，不用于填充当前检测结果。

默认 `desktop_auxiliary` 检查持久声明、生成规则、已启用内核 AND 规则及优先级，并识别把其他进程整体改道的已知宽泛声明。仅对当前快照中进程名和 `/Applications/Claude.app/` 路径均符合的样本判定桌面连接；分别报告 widget/hCaptcha 的 `actual_traffic_status`。无样本、单向或进程身份不足时保持 `UNVERIFIED`，不能用配置 PASS、Chrome 请求或历史 widget 成功代替 hCaptcha 实测。`active_test_status=NOT_RUN`：不打开帮助面板、不刷新、关闭连接、触发/完成验证码或发送消息。默认配置检查通过与实际流量待验证可以同时成立。

新增辅助规则仅加入审计基线与已知内核规则识别；现有 `repair` 命令范围不扩展，也不因本次 Skill 更新修改网络。以后辅助规则偏离时，先报告并在明确授权的局部范围处理。不得顺带扩展到所有 Intercom、所有进程、其他第三方或业务 DNS。

### Claude DNS 路径实测与默认观察

按 [Claude DNS 路径实测方法与边界](references/repair-and-verify.md#claude-dns-路径实测方法与边界) 复查。2026-10-22 首轮、21:49 复测及 22:03 再检测均未发现所测 Claude 路径绕过 IPRoyal；最新一轮为 12 次 DNS 查询、4 个新 TLS、8 个 Claude 域名连接样本，固定链权威对照仅见 Cloudflare，Google 仅见于普通美国01对照。分轮证据见引用记录，不累计样本；这是带时间和范围的实测结果，不是永久基线。

默认 `dns.claude_path_observations` 仅从现有连接分类 Claude 域名范围、代理链、双向数据和是否观察到 IPv6 目标；`FIXED` 是业务连接路径，不等于 DNS 已实测通过。`dns_path_status=UNVERIFIED`，实际 DNS、新 TLS、权威记录对照状态始终 `NOT_RUN`。无样本保留未核实，非固定样本需要进一步归因。此字段不改变原有业务配置判据，不新增主动请求或网络修复；实际检测须使用新证据，不能把任何一轮历史样本写成当前结果。

## 语言、时区和固定 IP 定位

见 [语言、时区与定位记录](references/repair-and-verify.md#语言时区与定位记录)。2026-10-20 用户授权后，Mac 已保存英语（美国）优先、中文第二及 `America/New_York`；Chrome 首选语言和重启后的 `Intl locale` 尚未核实。两家数据库对 `207.90.214.106` 的当次定位分别为 Ashburn / Washington，时区均为 `America/New_York`，不采用其他出口的洛杉矶定位。

默认只读比较并分别报告系统设置、浏览器设置、页面检测和数据库查询日期。`audit` 已提供上述本地语言/地区及时区观察；它不检测浏览器 Intl、运行中应用的有效语言或在线定位，原有配置 PASS 也不覆盖这些项目。用户仅要求检测或更新 Skill 时，不改语言、地区、时区，不重启 Mac/Chrome，也不因 `zh-CN`、城市标签差异自动修复。固定 IP 定位是可变的数据库结果，不是精确物理位置或永久强制基线；需要复查时只查询已确认的 Claude 出口 IP。

## 旧账号桌面偏好的历史清理与只读复查

仅在用户询问这次偏好清理或其保留情况时，读取 [2026-10-23 清理范围、备份与复查记录](references/desktop-old-preferences-20261023.md)。仅删除旧账号 4 个偏好成员、保留旧组织 3 个策略缓存的范围不变；该记录不改变本 Skill 的网络维护范围，也不授予再次清理或退出应用的权限。首轮 07:42 曾观察到写回；用户随后授权正常退出并重新备份，08:01 再清理，08:02 末次验证相关进程为空、4 项缺席且保留项未变。后续只读复查使用文档中的退出后新备份与验证哈希，不用首轮哈希覆盖最新状态。默认只读核对成员缺席、当前账号、策略缓存及受保护文件；不启动或退出 Claude、不读取钥匙串、不调用本地或远端 API，不运行网络检测脚本。未验证下次启动后的表现，历史通过不代表未来不会写回或 MCP 在线功能已验证。

## Claude Code 本地 ID 与钥匙串的历史记录

用户询问本次 `userID`、`machineID` 清理或 `Claude Code-credentials` 是否应保留时，读取 [2026-10-23 本地 ID 清理与钥匙串核实记录](references/code-local-ids-and-keychain-20261023.md)。21:24 用户授权备份后仅删除 `~/.claude.json` 顶层两个 ID，保留当前 `oauthAccount`、MCP、项目、记忆及网络配置；这更新了此前“保留两个 ID”的当次范围，不授权重复删除或清空其他账号数据。后续比较旧保护清单时，应将该文件的已批准变化与意外改动分开归因。

当次钥匙串条目仅含 `mcpOAuth`：26 项访问令牌为空，但 18 项含客户端 ID、3 项含非空客户端密钥；未发现 Claude 主登录块或可区分新旧 Claude 账号的身份字段。用户明确选择保留整条记录，不能因条目名称或空访问令牌将其当作无用旧登录凭据删除。默认复查仅做本地 JSON、备份和哈希比较，不访问钥匙串、不启动 Claude、不请求本地或远端 API，也不执行网络审计脚本。历史核实不证明当前钥匙串仍未变化、MCP 在线授权有效、全部旧授权已清除或下次启动不会重新生成 ID；必要时分别保留未验证状态。此引用不改变现有网络检查、脚本、基线或修复范围。

2026-10-23 21:30 的纯本地复查确认两个 ID 当时仍缺席，当前账号记录未变，170 个非目标受保护路径匹配清理基线；仅查钥匙串元数据确认条目保留，未再读秘密。随后更新文档时，21:32 发现 Claude 主进程已于 21:31:53 启动，两个 ID 已重新出现且均不同于清理前值，同时两项功能缓存及两份桌面本地文件发生变化；当前账号记录一致、4 个旧账号偏好仍缺席。任务未启动应用，启动来源未追查。详见引用文档中“21:30 只读复查”及后续观察，不能沿用较早通过结果宣称 ID 持续缺席，也不能据此认定旧账号授权恢复。未再次清理；历史快照、元数据与在线功能验证仍分开报告。

## 有修复授权时

详见 [references/repair-and-verify.md](references/repair-and-verify.md)。优先使用脚本处理已明确的持久规则偏离：

```bash
python3 ~/.codex/skills/mac-claude-network/scripts/check_claude.py repair
```

该命令先计算最小差异、建立 0700 私有备份、保存哈希、用本机 Mihomo 校验候选，再仅改当前订阅的规则扩展。已有正确配置不写入、不制造备份。**脚本不自动重载，打印 `reload_required` 不等于修复完成。** 继续用可用的原生 UI 工具在 Clash Verge“订阅”中重新激活同一订阅，回读内核规则和策略组，再完成实际验证。此 UI 操作属于已授权修复的一部分。

DNS 检查不会自动生成 DNS 修复，也不会因历史基线恢复邮件的旧私有 hosts。`repair` 仍仅处理既有路由例外；DNS 偏离须单独说明范围并获得修改 DNS 的授权，不能因调用 Skill 或配置检查失败就改公网/公司（含 OA/NC/邮件）/飞书 DNS。不得为了普通检测页评分删除已批准的飞书例外。用户只要求更新 Skill 时，也不允许修改网络配置。

固定节点缺失、凭据失效、代理字段或组选择错误、TUN/模式错误等，按引用文档逐项处理；只在身份明确、有原值及最小变更可验证时修复。不能自动覆盖复杂订阅脚本或扩大域名范围。结构变化时交付具体阻碍，保留已完成的独立检查。

## 交付与停止

分开汇报：配置检查、内核生效、DNS 配置与实际泄露测试、公司 DNS 保留与内网可达性、邮件 DNS/未认证连接与实际收发、Claude 网页出口、桌面实际连接、Google/Cloudflare STUN 候选结果、Code/MCP 保留情况。用户问到语言、Intl、时区或定位时，再按上述记录分别核对，不能用网络 PASS 代替。列出修复内容和可点击的备份/报告路径；未跑到的项目标注未核实。

第三方红色评分、IDC 标签、中文语言、Asia/Shanghai 时区不构成此 Skill 的修复失败判据。IPRoyal 固定 ISP 不等同家庭宽带，网络符合要求不保证账号不会验证或封禁。只验证明确主机及当次连接，不宣称所有应用/所有 IPv6 路径都已验证。
