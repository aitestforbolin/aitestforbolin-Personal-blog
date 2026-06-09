# 创建个人网站并上传到 GitHub Pages

## 1. 准备网站文件

在本地新建一个文件夹，例如：

```text
个人网站
```

里面至少放 3 个文件：

```text
index.html
styles.css
script.js
```

其中：

```text
index.html 负责网页结构
styles.css 负责页面样式
script.js 负责文章数据和简单交互
```

## 2. 创建 GitHub 仓库

打开 [GitHub](https://github.com)，点击右上角：

```text
+ → New repository
```

填写仓库名，例如：

```text
aitestforbolin-Personal-blog
```

选择：

```text
Public
```

然后点击：

```text
Create repository
```

## 3. 上传本地文件

进入刚创建好的仓库页面。

点击：

```text
Add file → Upload files
```

把本地网站文件拖进去：

```text
index.html
styles.css
script.js
```

页面底部填写提交信息，例如：

```text
Add personal blog homepage
```

点击：

```text
Commit changes
```

## 4. 开启 GitHub Pages

进入仓库页面，点击：

```text
Settings → Pages
```

找到：

```text
Build and deployment
```

设置：

```text
Source: Deploy from a branch
Branch: main
Folder: /root
```

然后点击：

```text
Save
```

## 5. 等待部署完成

GitHub Pages 第一次部署通常需要 1-3 分钟。

部署完成后，网站地址一般是：

```text
https://你的用户名.github.io/你的仓库名/
```

这次网站地址是：

```text
https://aitestforbolin.github.io/aitestforbolin-Personal-blog/
```

## 6. 以后自动更新网站

Codex 默认约定：

只要用户要求运行每日早报更新，就必须自动完成 GitHub Pages 发布，不停在本地文件生成，也不要求用户手动上传。

当前网站有两个早报频道：

```text
中国：个人网站/briefings/index.html
全球：个人网站/briefings/global.html
```

每次更新后，Codex 应同步检查并更新：

```text
个人网站/index.html
个人网站/briefings/index.html
个人网站/briefings/global.html
个人网站/briefings/当天中国早报.html
个人网站/briefings/当天全球早报.html
```

如果只更新其中一个频道，则只需要更新该频道详情页、对应归档页和首页。

优先发布方式：

```text
使用 Codex 的 GitHub 连接器写入 aitestforbolin/aitestforbolin-Personal-blog
```

原因：

```text
本机 git push 可能缺少命令行凭据，但 Codex GitHub 连接器已经授权写入仓库。
```

早报生成完成后，不需要再手动上传文件。让 AI 代理执行：

```bash
python3 早报/publish_mainland_briefing.py 早报/当天大陆早报.json
```

这个脚本会自动完成：

1. 把大陆早报 JSON 导出成网站页面
2. 更新 `个人网站/briefings/index.html` 归档
3. 更新首页的“本期早报”入口
4. 在 `个人网站` 目录里提交 Git 变更
5. 推送到 GitHub 仓库

默认仓库：

```text
https://github.com/aitestforbolin/aitestforbolin-Personal-blog.git
```

如果仓库地址以后变了，可以这样指定：

```bash
python3 早报/publish_mainland_briefing.py 早报/当天大陆早报.json --remote https://github.com/用户名/仓库名.git
```

推送成功后，GitHub Pages 通常等一两分钟就会更新线上网站。
