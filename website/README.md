# Code Ontology 宣传网站

公开地址：<https://hippop.github.io/code-ontology/>

独立静态网站，不依赖工作台、Node 构建、外部字体、第三方脚本或后端服务。
仅发布本目录，不发布项目数据库、运行目录或未提交的业务实现。

## 内容与边界

- 目标愿景：让业务语义贯穿需求、设计、代码与验证。
- 核心方法：五阶段交互讲解，含语义关系图。
- 真实案例：2026-09-08 任务优先级切片的历史验收摘要。
- 演进路线：分别标记已验证能力、下一步设计与长期愿景。
- `case-data.json` 为公开摘要，不能代替完整原始产物的独立复核。

## 本地预览

在仓库根目录运行：

```bash
python3 -m http.server 8091 --bind 127.0.0.1 --directory website
```

打开 <http://127.0.0.1:8091/>。无需安装依赖。发布前运行：

```bash
python3 scripts/check_website.py
node --check website/app.js
```

## GitHub Pages 发布

网站源码保存在 `main` 的 `website/`，发布分支为 `gh-pages` 根目录。
GitHub Pages 配置为 **Deploy from a branch → gh-pages → / (root)**。
不使用需要额外 OAuth workflow scope 的自定义工作流。

修改网站、检查通过后，先明确提交 `website/` 和相关网站脚本，再运行：

```bash
bash scripts/publish-website.sh
```

脚本只发布已提交的 `website/` 子树，通过非强制推送保护远端历史。
它不会自动提交、切换分支、修改用户工作区或发布未提交文件。
首次站点启用须由有管理权限的账号设置 Pages source；已有站点不应随意改写配置。

GitHub 官方说明：[从分支配置发布源](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)。
