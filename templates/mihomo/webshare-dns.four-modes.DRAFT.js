// 四模式 v3；配置生成扩展。修改本文件不会自动生效，须按发布流程重新生成。
// 每次必须输入原始机场订阅。生成结果带 x-webshare-generated 标记，禁止重复扩展。
// 设置方式：只修改下面三个模式开关。DNS/QUIC 根据模式自动设置，无需手动修改。
//
// ONLY_SECOND_HOP=true：业务流量仅 Webshare，系统例外直连；优先级最高。
// ONLY_SECOND_HOP=false, ENABLE_TWO_HOP=false：原订阅分流，代理部分仅机场第一跳。
// ONLY_SECOND_HOP=false, ENABLE_TWO_HOP=true, USE_THREE_TIER=false：原机场 TCP 全部追加 Webshare。
// ONLY_SECOND_HOP=false, ENABLE_TWO_HOP=true, USE_THREE_TIER=true：仅名单 TCP 两跳，其余沿用原分流。
// 原订阅 DIRECT/REJECT 在后三种模式中保留；TX 的 Baostock 第一跳特例也保持原行为。
// 此模式的业务 TCP 直接连接 Webshare；不支持的业务流量拒绝，不自动换出口。
// 用户选择保留系统例外直连；TX 生成器后置维护这些例外，本草稿不自行添加系统例外。
// 注意：“全面两跳”指原机场代理范围的 TCP，并非全部系统流量。
//
// 模式1：业务流量仅 Webshare，系统例外直连：ONLY_SECOND_HOP=true；业务 DNS 经 Webshare，业务 UDP 拒绝。
// 模式2：按规则走第二条：false, true, true；名单TCP走第一跳+Webshare；DNS/名单QUIC阻断开启。
// 模式3：只走第一条：false, false, 任意；DNS开启，不额外阻断QUIC。
// 模式4：全走两条：false, true, false；原机场TCP全部追加Webshare；DNS/对应范围QUIC阻断开启。
// 当前部署选择模式2（三档）；另外三种模式尚未完成真实运行验收。
const ONLY_SECOND_HOP = false;
const ENABLE_TWO_HOP = true;
const USE_THREE_TIER = true;

// 自动策略，勿单独设置：所有模式启用DNS增强；有Webshare的模式才追加QUIC阻断。
const ENABLE_DNS_PRIVACY = true;
const BLOCK_TWO_HOP_QUIC = ONLY_SECOND_HOP || ENABLE_TWO_HOP;

// DNS只作用于Mihomo接管的查询，应用自带DoH及未进入内核的流量不由本开关保证。
// Webshare不支持UDP；阻断UDP 443只是促使支持的应用回退TCP，不提供UDP代理能力。
// TX生成器后置系统DIRECT/DNS例外及TUN绕过规则未在本次草稿中修改。
// 本文件含私人连接参数，请勿公开；向用户发送的review版本使用占位符。
// 原DNS中需要保留的明确内网域名策略键：
const LOCAL_DNS_POLICY_KEYS = [];
const FIRST_HOP_GROUP = "机场第一跳";
const WEBSHARE = {
  "type": "socks5",
  "server": "192.0.2.10",
  "port": 7242,
  "username": "REPLACE_WITH_WEBSHARE_USERNAME",
  "password": "REPLACE_WITH_WEBSHARE_PASSWORD",
  "udp": false
};

// 接受原始机场订阅，不接受本脚本已生成的 YAML。
// 此标记随 YAML 保存；Mihomo 会忽略 x-* 扩展字段，脚本用它阻止重复处理。
const GENERATED_CONFIG_KEY = "x-webshare-generated";
function assertOriginalSubscription(config) {
  if (!config || !Array.isArray(config.rules)) throw new Error("订阅配置缺少 rules，停止应用");
  if (Object.prototype.hasOwnProperty.call(config, GENERATED_CONFIG_KEY))
    throw new Error("输入已由 Webshare 扩展生成，请从原始机场订阅重新生成，不要使用 active/config.yaml 或手机成品 YAML");
  const generatedName = value => typeof value === "string" &&
    (value === "二跳-webshare-名单" || value === "Webshare-仅第二跳" || value.startsWith("Webshare-TCP二跳 · "));
  const entries = [].concat(config.proxies || [], config["proxy-groups"] || []);
  if (entries.some(entry => entry && (generatedName(entry.name) ||
      (Array.isArray(entry.proxies) && entry.proxies.some(generatedName)))))
    throw new Error("输入含旧版 Webshare 扩展节点，请提供原始机场订阅");
  // 兼容旧版没有标记的两跳产物：即使节点已被删掉，也拒绝遗留规则或 DNS 引用。
  const containsGeneratedReference = value => {
    if (typeof value === "string") return /(?:,|#)(?:二跳-webshare-名单|Webshare-仅第二跳|Webshare-TCP二跳 · )/.test(value);
    if (Array.isArray(value)) return value.some(containsGeneratedReference);
    if (value && typeof value === "object") return Object.keys(value).some(key => containsGeneratedReference(value[key]));
    return false;
  };
  if ([config.rules, config["sub-rules"], config.dns].some(containsGeneratedReference))
    throw new Error("输入含旧版 Webshare 扩展规则或 DNS 引用，请提供原始机场订阅");
}
function markGenerated(config, mode) {
  config[GENERATED_CONFIG_KEY] = {version: "four-modes-v3", mode: mode};
  return config;
}

function parseIPv4Address(value) {
  const parts = value.split(".");
  if (parts.length !== 4 || parts.some(x => !/^\d{1,3}$/.test(x) || Number(x) > 255 || (x.length > 1 && x[0] === "0")))
    throw new Error("IPv4 格式错误：" + value);
  return parts.map(Number);
}
function parseIPv6Address(value) {
  if (!value || value.includes("%") || !/^[0-9a-f:.]+$/i.test(value)) throw new Error("IPv6 格式错误：" + value);
  let text = value.toLowerCase();
  if (text.includes(".")) {
    const pos = text.lastIndexOf(":"), b = parseIPv4Address(text.slice(pos + 1));
    text = text.slice(0, pos + 1) + (b[0] * 256 + b[1]).toString(16) + ":" + (b[2] * 256 + b[3]).toString(16);
  }
  const halves = text.split("::");
  if (halves.length > 2) throw new Error("IPv6 格式错误：" + value);
  const left = halves[0] ? halves[0].split(":") : [];
  const right = halves.length === 2 && halves[1] ? halves[1].split(":") : [];
  let words;
  if (halves.length === 2) {
    const missing = 8 - left.length - right.length;
    if (missing < 1) throw new Error("IPv6 格式错误：" + value);
    words = left.concat(Array(missing).fill("0"), right);
  } else words = left;
  if (words.length !== 8 || words.some(x => !/^[0-9a-f]{1,4}$/.test(x))) throw new Error("IPv6 格式错误：" + value);
  const bytes = [];
  for (const word of words) { const n = parseInt(word, 16); bytes.push(Math.floor(n / 256), n % 256); }
  return bytes;
}

// 三档、仅第一跳、全面两跳共享 DNS 策略；调用参数决定解析出口。
function enhancedDNS(input, sourceRules, defaultVia, chosenDomains, selectedHop) {
  const domestic = ["https://223.5.5.5/dns-query#DIRECT", "https://223.6.6.6/dns-query#DIRECT"];
  const encryptedVia = name => ["https://1.1.1.1/dns-query#" + name, "https://1.0.0.1/dns-query#" + name];
  const old = input.dns || {}, dns = Object.assign({}, old);
  const providers = input["rule-providers"] || {};
  const policy = {};
  const retainedLocal = {};
  const scopedKey = key => typeof key === "string" &&
    /^(?:(?:\+|\*)\.)?[a-z0-9_-]+(?:\.[a-z0-9_-]+)+\.?$/i.test(key);
  const privateResolver = value => {
    if (typeof value !== "string") return false;
    let host = value.split("#")[0].replace(/^(?:https|tls|tcp|udp):\/\//, "").split("/")[0];
    if (host[0] === "[") host = host.slice(1, host.indexOf("]"));
    else if (host.split(":").length <= 2) host = host.split(":")[0];
    if (/^(?:fc|fd)[0-9a-f]{2}:|^fe[89ab][0-9a-f]:|^::1$/i.test(host)) return true;
    const octets = host.split(".");
    if (octets.length !== 4 || octets.some(x => !/^\d{1,3}$/.test(x) || Number(x) > 255)) return false;
    const b = octets.map(Number);
    return b[0] === 10 || b[0] === 127 || (b[0] === 172 && b[1] >= 16 && b[1] <= 31) ||
      (b[0] === 192 && b[1] === 168) || (b[0] === 169 && b[1] === 254) ||
      (b[0] === 100 && b[1] >= 64 && b[1] <= 127);
  };
  const oldPolicy = old["nameserver-policy"] || {};
  for (const key of LOCAL_DNS_POLICY_KEYS) {
    if (!scopedKey(key)) throw new Error("内网 DNS 例外必须是范围明确的域名，不能填通配兜底或规则集：" + key);
    if (!Object.prototype.hasOwnProperty.call(oldPolicy, key)) throw new Error("原订阅 DNS 策略没有此例外项：" + key);
  }
  const localKey = key => /(^|[.+])(?:lan|local|localhost|arpa)$/.test(key) ||
    key === "localhost" || key === "rule-set:private_domain";
  // 保留旧策略的匹配范围和 DoH/DoT 服务商，但统一加密出口。
  // 不盲目保留旧 #DIRECT、明文 DNS、skip-cert-verify 或 ECS 参数。
  for (const key of Object.keys(old["nameserver-policy"] || {})) {
    const original = old["nameserver-policy"][key];
    if (localKey(key)) { policy[key] = Array.isArray(original) ? original.slice() : original; retainedLocal[key] = policy[key]; continue; }
    const values = Array.isArray(original) ? original : [original];
    if (LOCAL_DNS_POLICY_KEYS.includes(key) || (scopedKey(key) && values.length && values.every(privateResolver))) {
      policy[key] = values.slice();
      retainedLocal[key] = values.slice();
      continue;
    }
    const secure = values.filter(v => typeof v === "string" && /^(https|tls):\/\//.test(v));
    policy[key] = secure.length === values.length && secure.length ?
      secure.map(v => v.split("#")[0] + "#" + defaultVia) : encryptedVia(defaultVia);
  }
  // 从原规则识别直连域名、GEOSITE、域名规则集，不要求固定叫 cn_domain。
  for (const rule of sourceRules) {
    if (typeof rule !== "string") continue;
    const parts = rule.split(",").map(s => s.trim());
    while (["no-resolve", "src"].includes(parts[parts.length - 1])) parts.pop();
    if (parts.length !== 3 || parts[2] !== "DIRECT") continue;
    const type = parts[0].toUpperCase(), value = parts[1];
    if (type === "DOMAIN") policy[value.toLowerCase()] = domestic.slice();
    if (type === "DOMAIN-SUFFIX") policy["+." + value.toLowerCase()] = domestic.slice();
    if (type === "GEOSITE") policy["geosite:" + value] = domestic.slice();
    if (type === "RULE-SET" && providers[value] &&
        ["domain", "classical"].includes(providers[value].behavior))
      policy["rule-set:" + value] = domestic.slice();
  }
  if (providers.cn_domain) policy["rule-set:cn_domain"] = domestic.slice();
  if (providers.private_domain) policy["rule-set:private_domain"] = ["system"];
  // 显式域名名单优先于同名旧条目；fake-ip/远程 SOCKS 解析时，不保证每次都产生上游查询。
  for (const entry of chosenDomains || [])
    policy[entry.type === "DOMAIN-SUFFIX" ? "+." + entry.value : entry.value] = encryptedVia(selectedHop);
  for (const local of ["+.lan", "+.local", "localhost", "+.localhost", "+.arpa"])
    policy[local] = ["system"];
  // 保留的内网策略最后恢复，避免被自动 DIRECT/国内域名策略覆盖。
  // 与两跳域名名单相冲突时明确报错，而不是静默挑选一边。
  for (const key of Object.keys(retainedLocal)) {
    const stem = key.replace(/^(?:\+|\*)\./, "").replace(/\.$/, "").toLowerCase();
    const suffix = /^(?:\+|\*)\./.test(key);
    for (const entry of chosenDomains || []) {
      const domain = entry.value.toLowerCase(), chosenSuffix = entry.type === "DOMAIN-SUFFIX";
      const conflict = domain === stem || (suffix && domain.endsWith("." + stem)) ||
        (chosenSuffix && stem.endsWith("." + domain));
      if (conflict) throw new Error("两跳域名名单与保留的内网 DNS 策略冲突：" + key);
    }
    policy[key] = retainedLocal[key];
  }
  dns.enable = true;
  dns["prefer-h3"] = false;
  dns["respect-rules"] = false;
  dns["default-nameserver"] = domestic.slice();
  dns["proxy-server-nameserver"] = domestic.slice();
  dns["proxy-server-nameserver-policy"] = {};
  dns["direct-nameserver"] = domestic.slice();
  // DIRECT 出口再解析时也必须遵守内网策略，否则 fake-ip 下仍可能丢失内部解析。
  dns["direct-nameserver-follow-policy"] = true;
  dns.nameserver = encryptedVia(defaultVia);
  dns.fallback = [];
  delete dns["fallback-filter"];
  dns["nameserver-policy"] = policy;
  return dns;
}
function dnsHijack(tun) {
  const entries = Array.isArray(tun["dns-hijack"]) ? tun["dns-hijack"].slice() : [];
  for (const entry of ["any:53", "tcp://any:53"]) if (!entries.includes(entry)) entries.push(entry);
  return Object.assign({}, tun, {"dns-hijack": entries});
}

function main(config, profileName) {
  assertOriginalSubscription(config);
  if ([ONLY_SECOND_HOP, ENABLE_TWO_HOP, USE_THREE_TIER].some(value => typeof value !== "boolean"))
    throw new Error("三个模式开关必须是 true 或 false，不要加引号");
  if (ONLY_SECOND_HOP) return markGenerated(applySecondHopOnly(config), "business-webshare");
  let result;
  // 1. 只走第二条：上方提前返回 applySecondHopOnly。
  // 2. 按规则走第二条。
  if (ENABLE_TWO_HOP && USE_THREE_TIER) {
    result = applyThreeTier(config, profileName);
  // 3. 只走第一条。
  } else if (!ENABLE_TWO_HOP) {
    result = applyFirstHopOnly(config, profileName);
  // 4. 全走两条（原机场TCP范围，保留原DIRECT例外）。
  } else {
    result = applyAllProxy(config, profileName);
  }
  if (profileName !== "Android") {
    // TX 专用：Baostock 显式使用第一跳，优先于国内直连及第二跳规则。
    const baostockFirstHopRule = "DOMAIN-SUFFIX,baostock.com," + FIRST_HOP_GROUP;
    result.rules = [baostockFirstHopRule].concat(
      result.rules.filter(rule => rule !== baostockFirstHopRule)
    );
  }
  return markGenerated(result, !ENABLE_TWO_HOP ? "first" : USE_THREE_TIER ? "split" : "all");
}

// ===== 模式1：业务流量仅 Webshare，系统例外直连 =====
// 此模式控制进入 Mihomo 规则引擎的连接，不接管未进入内核的流量。
// 系统 DIRECT/DNS 例外应由 TX 生成器维护；未来发布时仍须适配生成器并校验最终产物。
function applySecondHopOnly(config) {
  if (!config || !Array.isArray(config.rules)) throw new Error("订阅配置缺少 rules，停止应用");
  // 要求 IP 字面量，避免连接 Webshare 前需要一次直连 DNS 引导。
  const host = String(WEBSHARE.server || "");
  try {
    if (host.includes(":")) parseIPv6Address(host);
    else parseIPv4Address(host);
  } catch (_) {
    throw new Error("业务流量仅 Webshare 模式要求 WEBSHARE.server 为合法 IPv4/IPv6 地址，不接受域名、方括号或区域标识");
  }
  if (WEBSHARE.type !== "socks5") throw new Error("仅第二跳模式目前只支持 Webshare SOCKS5");
  const name = "Webshare-仅第二跳";
  const result = Object.assign({}, config);
  const hop = Object.assign({}, WEBSHARE, {
    name: name,
    // DIRECT 仅指本机直连 Webshare 的底层连接，绝不是目标网站直连回退。
    "dialer-proxy": "DIRECT",
    udp: false
  });
  result.mode = "rule";
  result.proxies = [hop];
  result["proxy-groups"] = [];
  // 清除原有国内直连、Baostock 第一跳、名单、兜底与子规则；无机场依赖。
  result.rules = ["NETWORK,TCP," + name, "MATCH,REJECT"];
  delete result["sub-rules"];
  delete result["rule-providers"];
  delete result["proxy-providers"];
  // 此模式统一DNS经Webshare；与其余模式一样固定开启DNS增强。
  const resolvers = ["https://1.1.1.1/dns-query#" + name, "https://1.0.0.1/dns-query#" + name];
  result.dns = Object.assign({}, config.dns || {}, {
    enable: true,
    "prefer-h3": false,
    "respect-rules": false,
    "default-nameserver": resolvers.slice(),
    "proxy-server-nameserver": resolvers.slice(),
    "proxy-server-nameserver-policy": {},
    "direct-nameserver": resolvers.slice(),
    "direct-nameserver-follow-policy": false,
    nameserver: resolvers.slice(),
    fallback: [],
    "nameserver-policy": {}
  });
  delete result.dns["fallback-filter"];
  if (result.tun && typeof result.tun === "object") {
    const hijack = Array.isArray(result.tun["dns-hijack"]) ? result.tun["dns-hijack"].slice() : [];
    for (const entry of ["any:53", "tcp://any:53"]) if (!hijack.includes(entry)) hijack.push(entry);
    result.tun = Object.assign({}, result.tun, {"dns-hijack": hijack});
  }
  return result;
}

// ===== 模式2：按规则走第二条（名单两跳）=====
function applyThreeTier(config, profileName) {
  // DNS增强由模式固定开启。

  // 有第二跳时自动阻断对应范围UDP 443；仅第一跳不额外阻断。
  // 这不是断线保护；脚本报错后必须检查 Clash 是否仍在使用旧配置。

  // 原订阅中必须保留 system/dhcp:// 等内网 DNS 的策略键，按原键名填写。
  // 例如 ["+.corp.example.com"]。默认为空；不保留宽泛的本地 DNS 兜底。
  // 使用私有 IP DNS 且域名范围明确的旧策略会自动保留，不需要填这里。

  // ===== 修改区 1：第一跳代理组 =====
  // 订阅版默认“机场第一跳”；全局版默认留空，自动取当前配置 MATCH 的代理目标。
  // 有多个机场时，全局版仍取 MATCH 指定的那个；也可手动填写已有组名。
  // 若 MATCH 是 DIRECT / REJECT / SUB-RULE，无法自动识别，需手动填写。

  // ===== 修改区 2：两跳域名名单（3 个示例）=====
  // DOMAIN：只匹配这个域名；DOMAIN-SUFFIX：匹配该域名及全部子域名。
  // 仅填域名，不加 https://、路径、端口或 *。添加时复制一行，保留逗号。
  const TWO_HOP_DOMAINS = [
    { type: "DOMAIN", value: "ipv4.webshare.io" },
    { type: "DOMAIN-SUFFIX", value: "ifconfig.me" },
    { type: "DOMAIN-SUFFIX", value: "ipinfo.io" },
    { type: "DOMAIN-SUFFIX", value: "claude.com" },
    { type: "DOMAIN-SUFFIX", value: "claude.ai" },
    { type: "DOMAIN-SUFFIX", value: "platform.claude.com" },
    { type: "DOMAIN-SUFFIX", value: "api.anthropic.com" },
    { type: "DOMAIN-SUFFIX", value: "mcp-proxy.anthropic.com" },
    { type: "DOMAIN-SUFFIX", value: "downloads.claude.ai" },
    { type: "DOMAIN-SUFFIX", value: "storage.googleapis.com" },
    { type: "DOMAIN-SUFFIX", value: "registry.npmjs.org" },
    { type: "DOMAIN-SUFFIX", value: "formulae.brew.sh" },
    { type: "DOMAIN-SUFFIX", value: "raw.githubusercontent.com" },
    { type: "DOMAIN-SUFFIX", value: "github.com" },
    { type: "DOMAIN-SUFFIX", value: "code.claude.com" },
    { type: "DOMAIN-SUFFIX", value: "http-intake.logs.us5.datadoghq.com" },
    { type: "DOMAIN-SUFFIX", value: "browser-intake-us5-datadoghq.com" },
    { type: "DOMAIN-SUFFIX", value: "bridge.claudeusercontent.com" },
    { type: "DOMAIN-SUFFIX", value: "frame.claudeusercontent.com" },
    { type: "DOMAIN-SUFFIX", value: "claudeusercontent.com" },
    { type: "DOMAIN-SUFFIX", value: "fonts.googleapis.com" },
    { type: "DOMAIN-SUFFIX", value: "fonts.gstatic.com" },
    { type: "DOMAIN-SUFFIX", value: "cdnjs.cloudflare.com" },
    { type: "DOMAIN-SUFFIX", value: "cdn.jsdelivr.net" },
    { type: "DOMAIN-SUFFIX", value: "cdn.tailwindcss.com" },
    { type: "DOMAIN-SUFFIX", value: "code.jquery.com" },
    { type: "DOMAIN-SUFFIX", value: "unpkg.com" },
    { type: "DOMAIN-SUFFIX", value: "assets-proxy.anthropic.com" },
    { type: "DOMAIN-SUFFIX", value: "googlesource.com" },
    { type: "DOMAIN-SUFFIX", value: "anthropic.com" },
    { type: "DOMAIN-SUFFIX", value: "docs.claude.com" },
    { type: "DOMAIN-SUFFIX", value: "support.claude.com" },
    { type: "DOMAIN-SUFFIX", value: "google.com" },
    { type: "DOMAIN-SUFFIX", value: "google.co.jp" },
    { type: "DOMAIN-SUFFIX", value: "google.co.uk" },
    { type: "DOMAIN-SUFFIX", value: "googleapis.com" },
    { type: "DOMAIN-SUFFIX", value: "gstatic.com" },
    { type: "DOMAIN-SUFFIX", value: "googleusercontent.com" },
    { type: "DOMAIN-SUFFIX", value: "ggpht.com" },
    { type: "DOMAIN-SUFFIX", value: "gvt1.com" },
    { type: "DOMAIN-SUFFIX", value: "gvt2.com" },
    { type: "DOMAIN-SUFFIX", value: "gvt3.com" },
    { type: "DOMAIN-SUFFIX", value: "youtube.com" },
    { type: "DOMAIN-SUFFIX", value: "youtu.be" },
    { type: "DOMAIN-SUFFIX", value: "googlevideo.com" },
    { type: "DOMAIN-SUFFIX", value: "ytimg.com" },
    { type: "DOMAIN-SUFFIX", value: "youtube-nocookie.com" },
    { type: "DOMAIN-SUFFIX", value: "gmail.com" },
    { type: "DOMAIN-SUFFIX", value: "googlemail.com" },
    { type: "DOMAIN-SUFFIX", value: "appspot.com" },
    { type: "DOMAIN-SUFFIX", value: "run.app" },
    { type: "DOMAIN-SUFFIX", value: "web.app" },
    { type: "DOMAIN-SUFFIX", value: "firebaseapp.com" },
    { type: "DOMAIN-SUFFIX", value: "doubleclick.net" },
    { type: "DOMAIN-SUFFIX", value: "googlesyndication.com" },
    { type: "DOMAIN-SUFFIX", value: "googleadservices.com" },
    { type: "DOMAIN-SUFFIX", value: "google-analytics.com" },
    { type: "DOMAIN-SUFFIX", value: "googletagmanager.com" },
    { type: "DOMAIN-SUFFIX", value: "1e100.net" },
    { type: "DOMAIN-SUFFIX", value: "pki.goog" },
    { type: "DOMAIN-SUFFIX", value: "fuck-claude.vercel.app" },
  ];

  // ===== 修改区 3：两跳 IP 名单（3 个示例）=====
  // 以下为文档示例网段，不是可测试网站的真实 IP；使用前替换或删除。
  // 单个 IPv4 加 /32，单个 IPv6 加 /128；也支持 IPv4/IPv6 网段。
  // 私有、回环、链路本地、组播等网段及与它们重叠的宽网段会报错。
  // IP 规则带 no-resolve：不为匹配它额外解析域名；域名访问优先用上面的域名名单。
  const TWO_HOP_IPS = [
  ];

  // ===== 修改区 4：第二跳 Webshare（更换代理账号时修改）=====

  // ===== 以下是处理逻辑，通常无需修改 =====
  const HOP_NAME = "二跳-webshare-名单";
  if (!config || !Array.isArray(config.rules)) throw new Error("订阅配置缺少 rules，停止应用");
  // 本脚本只计算并返回新配置，错误时不改动传入对象。
  config = Object.assign({}, config);
  const dnsSourceRules = config.rules.slice();
  const nodes = Array.isArray(config.proxies) ? config.proxies : [];
  const groups = Array.isArray(config["proxy-groups"]) ? config["proxy-groups"] : [];
  const reserved = new Set(["DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL", "DNS"]);
  const available = new Set();
  for (const entry of nodes.concat(groups)) {
    if (entry && typeof entry.name === "string" && entry.name !== HOP_NAME &&
        !reserved.has(entry.name) && !["direct", "dns", "reject", "pass"].includes(String(entry.type || "").toLowerCase())) {
      available.add(entry.name);
    }
  }

  let firstHop = FIRST_HOP_GROUP.trim();
  if (!firstHop) {
    for (const rule of config.rules) {
      if (typeof rule !== "string") continue;
      const parts = rule.split(",");
      if (parts[0].trim().toUpperCase() === "MATCH") {
        const candidate = (parts[1] || "").trim();
        if (available.has(candidate)) firstHop = candidate;
        break; // 第一条 MATCH 才是实际兜底，不猜测其他机场组。
      }
    }
  }
  if (!available.has(firstHop)) {
    throw new Error("未找到可用第一跳代理组。请在 FIRST_HOP_GROUP 填写当前配置已有的代理组名。");
  }

  const normalizedDomains = [];
  function parseCIDR(value) {
    const parts = String(value).trim().split("/");
    if (parts.length !== 2 || !/^\d{1,3}$/.test(parts[1])) throw new Error("IP 名单必须填写 IPv4/IPv6 CIDR：" + value);
    const v6 = parts[0].includes(":"), bits = Number(parts[1]), max = v6 ? 128 : 32;
    if (bits > max) throw new Error("CIDR 前缀长度错误：" + value);
    return {bytes: v6 ? parseIPv6Address(parts[0]) : parseIPv4Address(parts[0]), bits: bits, v6: v6};
  }
  function overlaps(a, b) {
    if (a.v6 !== b.v6) return false;
    const n = Math.min(a.bits, b.bits), whole = Math.floor(n / 8), rest = n % 8;
    for (let i = 0; i < whole; i++) if (a.bytes[i] !== b.bytes[i]) return false;
    return !rest || Math.floor(a.bytes[whole] / Math.pow(2, 8 - rest)) === Math.floor(b.bytes[whole] / Math.pow(2, 8 - rest));
  }
  function checkedIP(value) {
    const cidr = String(value).trim(), parsed = parseCIDR(cidr);
    const blocked = parsed.v6 ? ["::/96", "::ffff:0:0/96", "fc00::/7", "fe80::/10", "ff00::/8"] :
      ["0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4"];
    // 同时拦截实际配置的 fake-ip 网段，防止把合成地址误填成公网目的地。
    const dnsConfig = config.dns || {};
    for (const key of ["fake-ip-range", "fake-ip-range6"]) {
      if (dnsConfig[key]) blocked.push(String(dnsConfig[key]));
    }
    if (blocked.some(range => overlaps(parsed, parseCIDR(range))))
      throw new Error("IP 名单与局域网、回环、链路本地或保留地址重叠：" + cidr);
    return {cidr: cidr, type: parsed.v6 ? "IP-CIDR6" : "IP-CIDR"};
  }

  const newRules = [];
  const seen = new Set();
  function addCondition(condition) {
    const rule = "AND,((NETWORK,TCP),(" + condition + "))," + HOP_NAME;
    if (BLOCK_TWO_HOP_QUIC) {
      const quic = "AND,((NETWORK,UDP),(DST-PORT,443),(" + condition + ")),REJECT";
      if (!seen.has(quic)) { newRules.push(quic); seen.add(quic); }
    }
    if (!seen.has(rule)) {newRules.push(rule); seen.add(rule);}
  }
  for (const entry of (ENABLE_TWO_HOP ? TWO_HOP_DOMAINS : [])) {
    const type = String(entry.type || "").trim().toUpperCase();
    const domain = String(entry.value || "").trim().toLowerCase();
    if (!["DOMAIN", "DOMAIN-SUFFIX"].includes(type) || !domain || /[\s,:/()*]/.test(domain)) {
      throw new Error("域名名单格式错误：仅使用 DOMAIN / DOMAIN-SUFFIX 和纯域名。");
    }
    if (/(^|\.)(lan|local|localhost|arpa)$/.test(domain)) throw new Error("本地域名不应加入两跳名单：" + domain);
    normalizedDomains.push({type: type, value: domain});
    addCondition(type + "," + domain);
  }
  for (const entry of (ENABLE_TWO_HOP ? TWO_HOP_IPS : [])) {
    const checked = checkedIP(entry);
    addCondition(checked.type + "," + checked.cidr + ",no-resolve");
  }

  const hop = Object.assign({name: HOP_NAME, "dialer-proxy": firstHop}, WEBSHARE);
  const existing = nodes.concat(groups).find(p => p && p.name === HOP_NAME);
  if (ENABLE_TWO_HOP && existing && Object.keys(hop).some(k => existing[k] !== hop[k])) {
    throw new Error("两跳节点名称冲突：" + HOP_NAME);
  }
  // 保留原订阅规则；入口已拒绝生成产物，此处只去重原输入中的相同规则。
  const originalRules = config.rules.filter(rule => !seen.has(rule));
  config.proxies = !ENABLE_TWO_HOP || existing ? nodes : nodes.concat([hop]);
  config.rules = newRules.concat(originalRules);
  // 保留 DNS 模式/过滤列表；不强制改 fake-ip 或打开嗅探。
  // redir-host 通过内核 DNS 映射也可恢复域名；应用绕过 Clash DNS 时可能无法命中域名名单。
  if (ENABLE_DNS_PRIVACY) {
    config.dns = enhancedDNS(config, dnsSourceRules, firstHop, normalizedDomains, HOP_NAME);
    if (config.tun && typeof config.tun === "object") config.tun = dnsHijack(config.tun);
  }
  return config;
}

// ===== 模式3：只走第一条 =====
function applyFirstHopOnly(config, profileName) {
  // ENABLE_TWO_HOP=false 时复用原分流实现，保留原DIRECT/REJECT及DNS增强。
  return applyThreeTier(config, profileName);
}

// ===== 模式4：全走两条（原机场TCP范围）=====
function applyAllProxy(config, profileName) {
  // DNS增强由模式固定开启。
  // 有第二跳时自动阻断对应范围UDP 443；仅第一跳不额外阻断。
  // 这不是断线保护；脚本报错后必须检查 Clash 是否仍在使用旧配置。
  // 原订阅中必须保留 system/dhcp:// 等内网 DNS 的策略键，按原键名填写。
  // 例如 ["+.corp.example.com"]。默认为空；不保留宽泛的本地 DNS 兜底。
  // 使用私有 IP DNS 且域名范围明确的旧策略会自动保留，不需要填这里。
  const TARGET_GROUP = FIRST_HOP_GROUP;
  const PREFIX = "Webshare-TCP二跳 · ";

  if (!config || !Array.isArray(config.rules)) throw new Error("订阅配置缺少 rules，停止应用");
  // 本脚本只计算并返回新配置，错误时不改动传入对象。
  config = Object.assign({}, config);
  const dnsSourceRules = config.rules.slice();
  const originalProxies = Array.isArray(config.proxies) ? config.proxies : [];
  const groups = Array.isArray(config["proxy-groups"]) ? config["proxy-groups"] : [];
  const reserved = new Set(["DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL", "DNS"]);
  const available = new Set();
  const allNames = new Set();
  for (const item of originalProxies.concat(groups)) {
    if (!item || typeof item.name !== "string") continue;
    allNames.add(item.name);
    const kind = String(item.type || "").toLowerCase();
    if (!reserved.has(item.name) && !item.name.startsWith(PREFIX) &&
        !["direct", "dns", "reject", "pass"].includes(kind)) available.add(item.name);
  }
  // 订阅版必须填原规则实际指向的组/节点；不能仅把 TARGET_GROUP 改 null 充当全局版。
  if (typeof TARGET_GROUP !== "string" || !available.has(TARGET_GROUP))
    throw new Error("未找到第一跳组，请将 TARGET_GROUP 填为原规则实际使用的代理组/节点名");
  const eligible = target => available.has(target) && target === TARGET_GROUP;
  const hops = new Map();
  const additions = [];

  function hopFor(target) {
    if (hops.has(target)) return hops.get(target);
    const name = PREFIX + target;
    if (allNames.has(name)) {
      const existing = originalProxies.find(p => p.name === name);
      // 只复用完全相同的本脚本节点，名称冲突则停止，防止循环/误引用。
      if (!existing || Object.keys(WEBSHARE).some(k => existing[k] !== WEBSHARE[k]) ||
          existing["dialer-proxy"] !== target) {
        throw new Error("Webshare 两跳节点名称冲突：" + name);
      }
    } else {
      additions.push(Object.assign({name: name, "dialer-proxy": target}, WEBSHARE));
      allNames.add(name);
    }
    hops.set(target, name);
    return name;
  }

  function parseRule(rule) {
    if (typeof rule !== "string") return null;
    const parts = rule.split(",");
    const flags = [];
    while (parts.length > 2 && ["no-resolve", "src"].includes(parts[parts.length - 1].trim())) {
      flags.unshift(parts.pop().trim());
    }
    if (parts.length < 2) return null;
    const target = parts.pop().trim();
    const type = parts[0].trim().toUpperCase();
    // 未识别的格式/规则不会改变。
    if (type === "SUB-RULE" || !eligible(target)) return null;
    const match = type === "MATCH";
    const condition = parts.join(",").trim();
    return {target: target, match: match, condition: condition, flags: flags};
  }

  function transform(rules) {
    const result = [];
    for (const rule of rules) {
      const parsed = parseRule(rule);
      if (parsed) {
        const hop = hopFor(parsed.target);
        // 原有 src/no-resolve 放进原条件中，保留其解析语义。
        const inner = parsed.condition + (parsed.flags.length ? "," + parsed.flags.join(",") : "");
        const tcpRule = parsed.match ? "NETWORK,TCP," + hop :
          "AND,((NETWORK,TCP),(" + inner + "))," + hop;
        if (BLOCK_TWO_HOP_QUIC) {
          const quic = parsed.match ? "AND,((NETWORK,UDP),(DST-PORT,443)),REJECT" :
            "AND,((NETWORK,UDP),(DST-PORT,443),(" + inner + ")),REJECT";
          // 局部去重；不能替代入口的原始订阅检查。
          if (result[result.length - 1] === tcpRule) result.pop();
          if (result[result.length - 1] !== quic) result.push(quic);
        }
        // 防止相邻生成分支重复；生成结果禁止再次输入。
        if (result[result.length - 1] !== tcpRule) result.push(tcpRule);
      }
      result.push(rule);
    }
    return result;
  }

  // 先在局部计算，发生名称冲突时不会先改写部分原配置。
  const newRules = transform(config.rules);
  const newSubRules = {};
  const subRules = config["sub-rules"];
  if (subRules && typeof subRules === "object") {
    for (const key of Object.keys(subRules)) {
      newSubRules[key] = Array.isArray(subRules[key]) ? transform(subRules[key]) : subRules[key];
    }
  }
  if (!hops.size) throw new Error("没有任何规则指向 " + TARGET_GROUP + "，两跳未生效");
  config.proxies = originalProxies.concat(additions);
  config.rules = newRules;
  if (subRules) config["sub-rules"] = newSubRules;
  // 保留 DNS 模式/过滤列表；不强制改 fake-ip 或打开嗅探。
  // redir-host 通过内核 DNS 映射也可恢复域名；应用绕过 Clash DNS 时可能无法命中域名名单。
  if (ENABLE_DNS_PRIVACY) {
    const hop = hops.get(TARGET_GROUP);
    if (!hop) throw new Error("DNS 两跳节点缺失，停止应用");
    config.dns = enhancedDNS(config, dnsSourceRules, hop, [], null);
    if (config.tun && typeof config.tun === "object") config.tun = dnsHijack(config.tun);
  }
  return config;
}

