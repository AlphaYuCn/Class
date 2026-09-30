# 部署到公网（Render 免费方案）

本项目已配置好 Render 一键部署，免费层足够班主任日常使用。

## 前置准备

1. 一个 **GitHub** 账号（免费）
2. 一个 **Render** 账号（免费，可用 GitHub 登录）：https://render.com

## 部署步骤

### 第一步：推送到 GitHub

1. 在 GitHub 新建一个仓库（如 `banzhuren`），**不要**勾选 README/.gitignore
2. 在本项目目录打开终端，执行：

```bash
git init
git add .
git commit -m "init: 班主任管理系统"
git branch -M main
git remote add origin https://github.com/你的用户名/banzhuren.git
git push -u origin main
```

> 注意：`.gitignore` 已配置，`instance/class.db` 和上传文件不会被推送。

### 第二步：Render 一键部署

1. 登录 Render → 点击右上角 **New +** → 选择 **Blueprint**
2. 选择你的 GitHub 仓库 `banzhuren`
3. Render 会自动读取 `render.yaml`，显示将要创建：
   - **Web Service** `banzhuren`（免费）
   - **PostgreSQL Database** `banzhuren-db`（免费，90天）
4. 点击 **Apply** 等待部署完成（约 3-5 分钟）

部署成功后，Render 会给你一个网址，如 `https://banzhuren-xxxx.onrender.com`，任何人都能访问。

## 数据迁移（可选）

如果想把本地已有数据搬到线上：

1. 先在本地导出数据（用 SQLiteStudio 或命令行）
2. Render 数据库的连接串在 Render 控制台 → banzhuren-db → Info → External Database URL
3. 用工具导入即可

> 注意：免费 PostgreSQL 90天后会过期，建议到期前导出备份。

## 常见问题

**Q: 免费层有什么限制？**
- Web 服务：512MB 内存，15分钟无访问会休眠，再次访问需等几秒
- PostgreSQL：90天免费，之后需升级（最低 $7/月）
- 上传文件会丢失（容器重启后），重要文件请下载到本地

**Q: 想长期免费怎么办？**
- 可改用 **PythonAnywhere**（免费层 SQLite 持久化，不丢数据，但国内访问慢）
- 或申请 **Render 学生包**（需 .edu 邮箱）

**Q: 想换自定义域名？**
- Render 免费层支持绑定自定义域名，在 Web Service → Settings → Custom Domains 添加

## 回退到本地使用

部署不影响本地使用，`python app.py` 仍可在本地运行（用 SQLite）。
