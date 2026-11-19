# OntoPoc 试点快速上手（一页）

给 3 到 8 人的团队（运营、财务、数据）在一台机器上做 2 周试点。需要 Python 3.11+ 和 Node 22+。

## 1. 安装并启动

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc
scripts/ontopoc-start.sh
```

脚本会建虚拟环境、打包页面、问你第一个管理员的账号和密码（至少 12 个字符），然后在 **http://127.0.0.1:8767** 启动服务。以后再运行一次就是重新启动。

如果你的代码里还没有这个脚本，手动来（见 [README.md](../../README.md)）：`python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[sources]'`，然后 `(cd landing-page && npm ci && npm run build)`，再 `PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin`，最后 `PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server`。

服务只听本机。别的电脑上的同事要用，前面放一个做 HTTPS 的代理（[docs/DEPLOY.md](../DEPLOY.md) 有 Caddy 和 nginx 的写法和 `--origin` 设置）；不要把 8767 端口直接开到网络上。

## 2. 加同事、分角色

用管理员登录，进入 **设置 > 用户 > 新建用户**。弹窗里有一段话（登录地址、用户名、初始密码），发给对方，初始密码只显示这一次；对方第一次登录必须改密码。

| 角色 | 能做什么 |
|---|---|
| 查看 | 看和提问；看不到原始数据行 |
| 建设 | 还能上传数据、建对象类型和管道、确认别人建的定义 |
| 管理员 | 还能管人、连数据库、设权限 |

**至少设两个“建设”。** 一份定义要由和提出人不同的另一位建设者确认；只有一个建设者时系统允许他自己确认，但日志会写明。试点建议：2 到 3 个建设（最懂数据的人），其余是只提问的查看。

## 3. 模型 key（可选）

```bash
export OPENROUTER_API_KEY=你的key     # 或 DEEPSEEK_API_KEY；在启动服务的那个终端里设
```

不要把 key 写进文件，也不要贴进聊天。**没有 key** 时，上传、定义、确认、待确认队列和各种检查都能用；关掉的是：对象类型建议、含义草稿，以及助手的自然语言回答（会提示缺 key）。模型只看到名称、类型、含义和取值少的列的取值，看不到数据行。

## 4. 数据在哪、怎么备份

用 `scripts/ontopoc-start.sh` 启动时全部在 `~/.ontopoc/data`（或 `ONTOPOC_DATA_DIR`）；手动启动时在检出目录的 `output/ontology-runs/`（或你用 `--data-dir` 指定的目录）：

| 文件 | 是什么 |
|---|---|
| `workspace.sqlite` | 全部数据集和版本、定义、确认记录、回答、日志，以及账号的密码哈希 |
| `sources.key` | 封存数据库密码的钥匙。丢了的话数据库来源要重新填 |

两样一起备份，**先停服务**，或用 `sqlite3 workspace.sqlite ".backup /备份路径/backup.sqlite"`。备份放在只有你能读的地方：sqlite 文件里有密码哈希。上传上限：一次 10 MB；一张表至多 100 万个单元格。

## 4b. 从 MySQL 或 PostgreSQL 读数据

管理员在 **数据 > 数据源** 里加数据库（需要 `pip install -e '.[sources]'`，启动脚本已经装好）。给 OntoPoc 一个只读账号。每张表读成一个数据集；**按主键更新** 会保留表里已删掉的行，**覆盖** 和表保持一致。

数据库在本机时加密默认 **不用**，否则默认 **必须（核对证书）**。“必须”会核对服务器证书*和它的主机名*。MySQL 自动生成的证书没有主机名，所以永远过不了，即使把它的 CA 贴进来也一样。数据库在别的机器上时，请 DBA 装一张按你连接用的主机名签发的证书（用公司 CA 签，把这个 CA 贴进数据源表单）。

## 5. 下一步

照 [FIRST_DEFINITION.md](FIRST_DEFINITION.md) 用 [sample/](sample/) 里的样例数据走一遍，再按 [README.md](README.md) 的日程推进。右上角头像菜单里有 **Send feedback**（中文界面显示“反馈意见”）；启动服务前设 `ONTOPOC_FEEDBACK_URL`，可以让它指向你们自己的表单或群。
