// Words the SERVICE sends in Chinese and the app has to recognise (it matches them; it does not show them). Kept apart from the converted files so those stay free of Chinese literals.
import { t } from "./i18n/index.js";

/** The kind of a reader of a dataset, as the service words it, mapped to the key of its name in the current language. */
const READER_KEY = { "管道": "pipeline", "对象类型": "objectType", "运行": "run", "关系": "relation", "视图": "view", "口径": "meaning", "重复键规则": "dupRule" };
export const PIPELINE_READER = "管道";
export const readerKindLabel = (kind) => (READER_KEY[kind] ? t(`data.reader.${READER_KEY[kind]}`) : kind);

/** The sentences the service says for a failed connection (source_connect.describe), each matched to the kind of failure. Order matters: the first match wins. */
export const CONNECT_PATTERNS = [
  ["host", /找不到这个主机名|名字解析|could not resolve this host/i],
  ["blocked", /元数据服务|内部地址|metadata service|internal address/i],
  ["driver", /程序包|pip install|driver package/],
  ["cert", /证书|TLS 握手|TLS handshake|certificate/i],
  ["tls", /不支持 TLS|refuses SSL|does not support TLS/],
  ["password", /用户名或密码|密码不对|认证|username or password|authentication/i],
  ["database", /没有这个数据库|no such database/i],
  ["timeout", /超时|超过时限|timed out|time limit/i],
  ["port", /被对方拒绝|连不上|没有应答|中途断了|refused the connection|no answer|dropped midway/i],
];

/** What a person may type between key columns: ASCII and full-width commas, the enumeration comma, spaces. */
export const KEY_SEPARATORS = /[,，、\s]+/;
