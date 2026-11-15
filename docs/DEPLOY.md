# 给一个团队用：部署要点

服务本身只听本机（127.0.0.1:8767），不处理 HTTPS。给几个人用时，前面放一个做 HTTPS 的代理，服务和数据都留在这台机器上。下面按顺序做。

## 1. 账号

在服务所在的机器上建第一个管理员（没有默认账号和密码）：

```bash
PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin    # 问账号和密码（至少 12 个字符）；忘了用同一工具的 reset-password
```

其他人由管理员在页面“用户”里建：**查看**只能看和提问，**建设**还能上传数据、改定义、确认别人的定义，**管理员**还能管人、数据源和权限。新账号第一次登录必须先改掉临时密码。给脚本和智能体用的令牌在“我的账号”里建；页面上新建时默认只读，要写的权限得自己选。

## 2. 模型 key

key 只放在启动服务的那个进程的环境变量里，不写进任何文件：

```bash
export OPENROUTER_API_KEY=...    # 或 DEEPSEEK_API_KEY；只有 OpenRouter 时默认用 deepseek/deepseek-v4.1-flash
```

本机用钥匙串管理 key 时，可以用 `hk run "OpenRouter" -- <启动服务的命令>`，key 只进这条命令的环境。服务启动时如果模型名和接口对不上，会在第一行说明。

## 3. 启动服务和 HTTPS 代理

```bash
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server \
  --data-dir /srv/ontopoc/data \
  --origin https://ontopoc.example.com
```

- `--origin`：页面所在的地址。只有这个地址发来的写请求会被接受；配了 https 的地址后，登录 cookie 带 Secure。可以写多个。
- `--trusted-proxy`：哪个地址的代理可以信。配了 https 的 `--origin` 时默认只信本机，代理和服务在同一台机器上就不用写。
- 页面在 `landing-page` 里用 `npm run build` 打包到 `landing-page/dist/client/`，由代理直接发出（团队应用是 `index.html`，早期界面是 `legacy.html`）；`/api/` 开头的请求转给服务。

Caddy：

```
ontopoc.example.com {
    handle /api/* {
        reverse_proxy 127.0.0.1:8767
    }
    handle {
        root * /srv/ontopoc/landing-page/dist/client
        try_files {path} /index.html
        file_server
    }
}
```

nginx（只列转发那一段）：

```
location /api/ {
    proxy_pass http://127.0.0.1:8767;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;    # 覆盖成代理看到的来访地址，不要追加客户端自己写的
}
```

服务只信 X-Forwarded-For 的最后一个地址，并按它算登录次数限制，所以代理必须覆盖这个头（nginx 如上），或者像 Caddy 那样在末尾追加它自己看到的地址。不要让客户端能直接连到 8767 端口。

`--no-auth`（关掉登录）只给自己机器上的试用，和 `--origin` 一起用会被拒绝。

## 4. 数据和备份

数据目录里要一起备份的两样：

| 文件 | 是什么 |
|---|---|
| `workspace.sqlite` | 全部数据集、定义、确认记录、回答、日志，以及账号的密码哈希和登录会话 |
| `sources.key` | 封存数据源密码的钥匙。没有它，数据源的密码读不出来，要重新填 |

两样文件只给运行服务的那个系统账号读写（服务启动时会收紧权限）。备份同样要放在只有自己能读的地方：拷走 `workspace.sqlite` 等于把密码哈希交了出去。备份时先停服务，或用 `sqlite3 workspace.sqlite ".backup /path/backup.sqlite"`。

## 5. 权限要注意的地方

- **行规则只管一个数据集。** 给对象类型加的行规则，限制的是读同一个数据集的那些类型的行。别的数据集里如果有同样的编号或金额（例如订单明细表里也有客户编号），要另外给那些类型加名单或行规则。
- **早期界面只给不受限制的人。** 按“运行”组织的早期界面（`legacy.html`、`/api/ontology/*`）存的是整张表，不按名单和行规则过滤；只有管理员和不受任何名单、行规则限制的建设者能打开，其他人用团队应用。
- **上传上限。** 单个文件或一次上传合计 10 MB；一个 CSV 或 Excel 至多 100 万个单元格；Excel 解压后至多 50 MB。超过时会说明原因，拆成几个文件即可。
- **登录次数。** 一小时内同一账号错 50 次会锁 15 分钟，管理员也一样；忘了密码在服务所在的机器上用 `reset-password`。

## 6. 上线前自检

```bash
curl -s https://ontopoc.example.com/api/ontology/health      # {"ok": true}
PYTHONPATH=src:. python3 scripts/real_model_check.py --out /tmp/check   # 在内置数据上对照 SQL 检查真实模型；只有错数才算失败
```
