# GitHub 蓝绿热部署

推送到 `main` 后，`.github/workflows/deploy-server.yml` 会先运行测试，再通过 SSH 通知生产服务器拉取该次提交并部署。服务器按提交 SHA 执行 `git fetch`，不会误部署后续提交，也不需要从 Actions Runner 传输完整源码包。

## GitHub Secrets

仓库需要配置以下 Actions Secrets：

- `XBOOM_SSH_HOST`：生产服务器地址。
- `XBOOM_SSH_PORT`：SSH 端口，默认使用 `22`。
- `XBOOM_SSH_USER`：部署用户。
- `XBOOM_SSH_PRIVATE_KEY`：仅用于部署的 Ed25519 私钥。

## 服务器布局

- `/www/wwwroot/xboom`：共享运行数据、密钥、虚拟环境和旧版兼容目录。
- `/www/wwwroot/xboom-releases/<commit>`：不可变源码版本。
- `/www/wwwroot/xboom-current`：当前版本软链接。
- `/www/wwwroot/xboom-runtime`：PID、部署锁、槽位日志和 Nginx 备份。
- `/www/wwwroot/xboom-git`：只用于按 SHA 增量拉取 GitHub 提交的本地 Git 缓存。

Web 服务在 `8001` 与 `8002` 两个槽位之间切换。新槽位先通过 `/health` 检查，Nginx 才会切流；失败时继续使用旧槽位。

定时任务不在 Web 进程中启动。`xboom-scheduler.service` 运行独立调度器，并通过共享数据目录中的 `flock` 文件锁保证单实例，避免蓝绿并行期间重复发送任务。

## 手动回滚

回滚到最近一个旧版本：

```bash
/www/wwwroot/xboom-current/scripts/rollback-blue-green.sh
```

回滚到指定提交：

```bash
/www/wwwroot/xboom-current/scripts/rollback-blue-green.sh <commit-sha>
```

回滚同样会先启动备用槽位并做健康检查，再切换 Nginx。
