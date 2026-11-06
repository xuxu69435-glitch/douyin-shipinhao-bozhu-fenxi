# 开发提交流程

在项目根目录检查修改内容，并创建本地提交：

```powershell
git status --short
git diff
git add .
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m '更新项目文档'
```

提交前确认暂存内容仅包含本次修改的源代码与文档，提交消息应描述实际变更。

本地提交完成后，检查当前分支和远端地址，再手动推送：

```powershell
git branch --show-current
git remote -v
git push
```

如推送被拒绝，先获取并审阅远端变更，再决定如何合并，避免强制覆盖已有提交。
