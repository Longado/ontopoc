# 登录与账号

从 [README](../README.md) 搬来。

服务默认要登录，没有默认账号和默认密码。第一次用先在服务所在的机器上建管理员：

```bash
PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin     # 问账号和密码（至少 12 个字符）；忘了密码用同一个工具的 reset-password
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --origin http://127.0.0.1:5178   # --origin：页面所在的地址（这里是开发服务器）；可重复
```

管理员在页面“用户”里建其他人：**查看**只能看和提问，**建设**还能上传数据、改定义，**管理员**还能管人。新账号第一次登录必须先改掉管理员给的临时密码。每一次操作都记在登录的人名下，请求里自己写的名字会被忽略。脚本和 MCP 用“我的账号”里创建的令牌（给 MCP 设环境变量 `ONTOPOC_TOKEN`），权限和令牌主人的角色一样。

**两人确认**：有两个以上的人能确认时，一个人提出的定义（含义、对象类型、关系、视图、行为、派生属性、管道）要另一个人确认才生效，提出的人自己不能确认；只有一个人能确认时自动不生效，日志里会标出自己确认自己的那几条。管理员可以在“用户”页关掉。用令牌改一条已确认的定义，哪怕只改名称或说明，它也要重新等人确认；用令牌做的写入，日志里每一行都写明是哪个令牌。

**给团队用**：服务本身只听本机，不处理 HTTPS。前面放一个做 HTTPS 的代理，例如 Caddy（完整步骤、备份和权限要点见 [docs/DEPLOY.md](DEPLOY.md)）：

```
ontopoc.example.com {
    reverse_proxy 127.0.0.1:8767
}
```

服务启动时加 `--origin https://ontopoc.example.com`：这个地址才会被接受，登录 cookie 带 Secure，登录次数限制按代理看到的来访地址算。非本机的 http 地址会被拒绝。`workspace.sqlite` 里有密码的哈希和登录记录，文件权限是仅本人可读写，拷贝给别人等于把哈希给了别人。代理要把它看到的来访地址写进 X-Forwarded-For（nginx：`proxy_set_header X-Forwarded-For $remote_addr;`），服务只信这个头的最后一个地址，且只信 `--trusted-proxy` 指定的代理（配了 https 的 `--origin` 时默认是本机）。

**只在自己机器上试**：`--no-auth` 关掉登录，所有请求都当作本机管理员，不要用在共用的机器上。要先设环境变量 `ONTOPOC_DEV=1`；和 `--origin` 一起用会被拒绝，带代理头（X-Forwarded-For 等）的请求也会被拒绝。
