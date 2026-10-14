# 发布与核验

## 工具和身份预检

先查询可用的社媒发布连接器；没有能完成身份、上传、预览和公开核验的连接器时，
使用当前支持的浏览器工具及已登录 Chrome。`cua_repl` 可能作为顶层工具提供；先调用
其文档指定的初始化 API，读返回文档后再操作。不要因旧的 `chrome:control-chrome`
未安装就声称无法控制浏览器，也不要导入旧运行时或猜测方法名。

在任何生成前打开并记录：

- Facebook：`https://www.facebook.com/profile.php?id=61575467138674`
- LinkedIn：`https://www.linkedin.com/company/146727123/admin/dashboard/`

核对数字 ID、页面显示的公司名、当前发布身份和创建帖子权限。可见名称允许正常语言
或品牌变体，但账号归属必须明确；保存实际观察，不预先声称已登录。
遇到登录、密码、MFA、CAPTCHA、身份选择器、权限不足或草稿恢复歧义立即停止。

### Facebook 一次两步切换

仅在已登录且目标页面明确提供切换到该同一主页的操作时：

1. 核对当前目标 ID 为 `61575467138674`，点击该页面中的切换动作一次。
2. 若出现确认对话框，仅当它明确显示同一目标主页时点击确认一次。
3. 导航完成后重开固定目标 URL，检查目标 ID、可见公司名、实际发布身份和创建按钮。

两步合计一次序列。若仍要求切换、出现其他账号列表或验证，则停止。不重复切换，
不改用个人账号或其他管理主页。

## 最终发布前

两个平台都要先确认具备权限；全部素材通过 `validate_campaign.py` 后才开始第一条。
各平台提交前再次确认身份，粘贴完整对应文案，上传 `social-upload.jpg`，检查预览。
如果当前模板或上传工具不能接受本地图片，记录阻塞，不擅自发布无图帖子。

## Facebook → LinkedIn

每个平台使用以下顺序，Facebook 先执行：

1. 打开固定目标页面的创建帖子操作；不从通用首页发帖。
2. 使用 `facebook.txt` 或 `linkedin.txt`，上传同一临时 JPEG。
3. 确认全部文本、产品链接、图片和作者身份，处理正常的预览步骤。
4. 紧邻最终提交前运行 `update_manifest.py --status pending --submission-started`。
5. 点击最终发布按钮一次。
6. 在目标页面时间线或已发布列表找到该条帖子，打开实际帖子链接核对文本、图片和作者。
7. 保存 `evidence/facebook-public.md` 或 `evidence/linkedin-public.md`，包含核验时间、
   数字身份、观察到的作者、公开 permalink、文案/图片一致性和浏览器截图路径（可用时）。
   私有后台 URL、首页、主页 URL 和仅有“已提交”提示不算公开发布证据。
8. 记录 `published`，例如：

```bash
python3 scripts/update_manifest.py MANIFEST --channel facebook --status published \
  --url FACEBOOK_POST_URL --identity-id 61575467138674 --evidence FACEBOOK_EVIDENCE
python3 scripts/update_manifest.py MANIFEST --channel linkedin --status published \
  --url LINKEDIN_POST_URL --identity-id 146727123 --evidence LINKEDIN_EVIDENCE
```

只有点击并查看实际记录后才写核验文件；状态脚本验证路径和身份字段，不能替代观察。
平台如提供不同但真实的永久链接结构，先核实其来源，再调整本技能 URL 校验器；
不得编造一个符合正则的 URL。短链接应打开后记录真实平台永久链接。

## 结果不明与续跑

若提交后超时或浏览器断开，保留永久提交标记，记录 `blocked` 及原因。
先查看该账号的已发布内容、时间、图片和完整文案进行核对。找到则记成功；只有取得
该条未发布的明确证据后才允许一次有记录的重试。仍不明确则停止，禁止试探性再点发布。
已发布渠道不可自动删除、回滚、重发，也不能重置为 pending。

一个渠道失败或阻塞时，停止后续提交并报告当前状态。用户明确要求恢复时再重新预检；
跳过 `published` 渠道，恢复同一产品与素材。两个社媒成功但表格失败时，仅修复表格记录。
双平台均成功后可以删除上传 JPEG，原有文件哈希和审核证据保留，完成检查不再要求 JPEG。
