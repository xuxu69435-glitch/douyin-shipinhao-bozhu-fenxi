# 提交到自己的 GitHub 仓库

本地仓库的 user.name 和 user.email 已使用本机原有的个人 Git 配置。两条未推送历史的 Author 和 Committer 都已改为 `xuxu69435`；原始历史另存于仓库外的 `.backups` 目录，不会推送。

无需重新复制工程或建立新仓库。工作目录仍是 `E:\1bishe\douyin-analyst-v5`，远端 origin 已配置为用户提供的仓库。本轮不推送。

以后在此仓库检查身份、内容并提交：

```powershell
Set-Location E:\1bishe\douyin-analyst-v5
git config --local --get user.name
git config --local --get user.email
git status --short
git add .
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m '描述本次实际修改'
git log -1 --format=full
```

Author 和 Commit 两项都应为自己的身份。提交消息不添加工具协作者尾注。

第一次推送前，检查远端内容及当前分支：

```powershell
git branch --show-current
git ls-remote --heads origin
```

当前分支为 main 且远端仍为空时，使用自己的 GitHub 登录执行：

```powershell
git push -u origin main
```

如远端已有其他提交，先获取并审阅，不强制推送覆盖。身份配置与 GitHub 登录是两件事：Git 配置决定提交记录中的身份；Git Credential Manager 登录决定谁有权限推送。

密钥、Cookie、模型设置、日志、媒体、虚拟环境、构建产物和安装包均不应进入源码提交。发布安装包应单独核对实际依赖的许可证、FFmpeg 对应源代码义务及模型权重许可。
