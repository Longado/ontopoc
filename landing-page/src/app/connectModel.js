// The connection guide's words, as plain data so they can be tested without a browser: the steps, what a failed connection most likely means and how to check it,
// and the text a person copies to send to their DBA. The service words each failure in one sentence (source_connect.describe); `diagnose` reads that sentence.
import { kindPort } from "./sourceModel.js";

export const STEPS = [
  { key: "type", label: "选类型" },
  { key: "connect", label: "填连接" },
  { key: "test", label: "测试" },
  { key: "tables", label: "选表" },
  { key: "schedule", label: "定时同步" },
];

/** The five things the guide names when a connection fails; each has a cause below. */
export const CHECKS = ["host", "port", "password", "cert", "timeout"];

/** Switching the type puts that type's usual port in the box. */
export const portAfterKind = (kind) => String(kindPort(kind));

const NETWORK = { what: "这台服务器到数据库之间的网络没放行", check: "让网络或运维同事确认：从运行 OntoPoc 的这台服务器，能不能访问数据库的地址和端口（防火墙、安全组、白名单）" };

const KNOWN = [
  { kind: "host", test: /找不到这个主机名|名字解析/, title: "找不到这个主机名",
    causes: [
      { what: "主机名拼错了", check: "对照数据库管理员给的地址，逐字核对，注意不要带 http:// 或端口" },
      { what: "运行 OntoPoc 的服务器解析不了这个内网名字", check: "在服务器上执行 nslookup 主机名；解析不出就改填 IP 地址，或请运维把名字加进 DNS" },
    ] },
  { kind: "blocked", test: /元数据服务|内部地址/, title: "这个地址不能当数据源",
    causes: [{ what: "填的是云服务商的内部地址（169.254 开头一类）", check: "换成数据库自己的地址" }] },
  { kind: "driver", test: /程序包|pip install/, title: "这台服务器还缺连接数据库的程序包",
    causes: [{ what: "服务器上没装对应的驱动", check: "请运维按提示安装后重启服务；这不是你填错了" }] },
  { kind: "cert", test: /证书|TLS 握手|TLS handshake|certificate/i, title: "加密连接的证书没通过",
    causes: [
      { what: "数据库用的是公司内部自签或内部 CA 签发的证书", check: "回到上一步：“加密连接”选“不用”（只限内网），或把公司 CA 的 PEM 文字贴进“CA 证书”" },
      { what: "证书过期，或证书上的名字和你填的主机名不一致", check: "让 DBA 查证书的有效期和它签给的主机名；用证书上的名字做主机" },
    ] },
  { kind: "tls", test: /不支持 TLS|refuses SSL/, title: "数据库没有开启加密",
    causes: [
      { what: "这个数据库只接受不加密的连接", check: "让 DBA 开启 TLS；或在内网里，把“加密连接”改成“不用”（密码和数据会明文过网络）" },
    ] },
  { kind: "password", test: /用户名或密码|密码不对|认证/, title: "账号或密码不对",
    causes: [
      { what: "账号或密码输错了（密码区分大小写）", check: "用同一个账号密码在别的数据库工具里登录一次；密码里有特殊字符时重新粘贴" },
      { what: "这个账号不允许从这台服务器登录", check: "让 DBA 确认账号的“允许来源”（MySQL 的 host 部分，PostgreSQL 的 pg_hba）包含这台服务器" },
    ] },
  { kind: "database", test: /没有这个数据库/, title: "没有这个数据库名",
    causes: [{ what: "数据库名拼错，或这个账号看不到它", check: "核对库名；让 DBA 确认账号对这个库有连接和 SELECT 权限" }] },
  { kind: "timeout", test: /超时|超过时限/, title: "等了很久没有应答",
    causes: [
      { ...NETWORK, what: "防火墙把包悄悄丢掉了，所以一直没有回应" },
      { what: "数据库太忙，或地址写成了一个不通的 IP", check: "确认地址是数据库所在机器；让 DBA 看数据库当时的负载" },
    ] },
  { kind: "port", test: /被对方拒绝|连不上|没有应答|中途断了/, title: "连不上这个地址和端口",
    causes: [
      { what: "端口不对", check: `PostgreSQL 通常是 5432，MySQL 通常是 3306；核对 DBA 给的端口` },
      { what: "数据库没有在这个地址上监听", check: "让 DBA 确认数据库已启动，并且允许远程连接（listen_addresses / bind-address 不能只写 localhost）" },
      NETWORK,
    ] },
];

const OTHER = {
  kind: "other", title: "没有连上",
  causes: [
    { what: "地址、端口、账号、密码里有一项不对", check: "逐项对照数据库管理员给的信息" },
    { ...NETWORK },
    { what: "数据库自己拒绝了这次连接", check: "把下面的错误信息复制给 DBA，请他看数据库的日志" },
  ],
};

/** What a failed connection most likely means: {kind, title, causes: [{what, check}]}, from the sentence the service sent. Anything not recognised gets the general checks. */
export function diagnose(message) {
  const text = String(message ?? "");
  const found = KNOWN.find((k) => k.test.test(text));
  const { kind, title, causes } = found ?? OTHER;
  return { kind, title, causes };
}

const TLS_WORD = { required: "必须（核对证书）", none: "不用" };

/** The text for "复制错误信息": enough for a DBA to act on, and never the password. */
export function errorReport({ source, kind, host, port, database, username, tls, message, at }) {
  return [
    `OntoPoc 连接数据库失败${at ? `（${at}）` : ""}`,
    `数据源：${source}`,
    `类型：${kind}`,
    `地址：${host}:${port}`,
    `数据库：${database}`,
    `账号：${username}`,
    `加密：${TLS_WORD[tls] ?? tls}`,
    `错误：${message}`,
  ].join("\n");
}
