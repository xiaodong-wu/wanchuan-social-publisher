# 发布与核验

## 工具和身份预检

以下浏览器预检适用于 live 发布；dry-run 不连接社媒。

使用浏览器插件操作已登录 Chrome，完成 Facebook 和 LinkedIn 的身份核验、图片上传、
文案填写、预览、最终提交和公开帖子核验。选择插件连接的扩展会话（例如 `cua_repl`
返回的 `type: extension` 浏览器），不使用社媒发布连接器或 API 代替浏览器发帖。

### 选择 Chrome 和标签页

1. 按插件说明读取浏览器清单（`cua_repl` 需要发现会话时从 `cua.getState()` 开始）。
   以返回的 `browsers` 和对应的 `errors` 为准；初始化日志出现警告但清单成功返回时继续判断。
   如已绑定本次任务的 Chrome 扩展，继续使用该绑定。首次选择时，以名称和 `type: extension`
   筛选 Chrome，再用本次实际返回的 ID 绑定。仅有一个匹配项时直接使用。遇到多个 Chrome 配置文件，
   优先用用户指定的配置文件，否则用目标标签页能唯一确定的配置文件。两者冲突、目标分属不同配置文件
   或仍有多个候选时，报告需要辨认的配置文件。列表顺序、活动窗口和历史 ID 都不能确定应选哪一个。
2. 在该扩展中列出标签页，优先使用当前任务已绑定且仍指向目标的页。否则从清单定位目标管理页；
   同一配置内有多个同目标页且无法分清时，仅在新批次预检另开固定入口，保留已有页面和草稿。
   已连接扩展的标签清单为空或只有其他页面时，也可在该扩展新开固定入口。续跑先读 manifest，
   有提交标记的渠道按“结果不明与续跑”核对。每个渠道分别保存标签页绑定。
3. 只根据解析后的 HTTPS 网址识别目标页。以下纯函数可在插件返回的标签清单上使用，
   只用于选择候选标签。其他地址从固定入口进入；不要把其他品牌标签改作万川页。

```js
function targetPage(rawUrl) {
  let url;
  try {
    url = new URL(rawUrl);
  } catch {
    return null;
  }
  if (url.protocol !== 'https:' || url.username || url.password || url.port) return null;
  const host = url.hostname.replace(/^www\./, '');
  const ids = url.searchParams.getAll('id');
  if (host === 'facebook.com' && url.pathname === '/profile.php' &&
      ids.length === 1 && ids[0] === '61575467138674') {
    return 'facebook';
  }
  if (host === 'linkedin.com' && /^\/company\/146727123\/admin(?:\/|$)/.test(url.pathname)) {
    return 'linkedin';
  }
  return null;
}
```

固定入口：

- Facebook：`https://www.facebook.com/profile.php?id=61575467138674`
- LinkedIn：`https://www.linkedin.com/company/146727123/admin/dashboard/`

### 在编辑器内核验发帖人

从固定目标进入创建流程，检查同一编辑器中的公司、受众和可编辑正文，再记录发帖权限。
公司通常显示为 `Shenzhen Vantrend Beauty Technology Co., Ltd.`，允许可与目标 ID 核对的本地化名称。
Facebook 可见入口如“分享新鲜事”，编辑器应显示万川为作者。LinkedIn 从公司管理员页进入
“创建 → 发动态”，同一公司 ID 的 `admin/page-posts/` 也可使用。核对编辑器中的作者按钮和
“发布到任何人”或等价受众标识。后台标题、个人头像、评论身份、其他帖子的作者都不能代替这一步。
若发现现存草稿、登录、MFA、验证码、权限拒绝或无法辨明的身份选择器，停止并记录所见。
Facebook 页面明确指向万川的切换按下节处理。

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

### 页面加载和控件失效

- **导航或读取超时。** 先在已绑定的扩展内重新列出标签，并读取目标页当前状态。若页面已到达，
  从可见界面继续；若仍在加载，按插件文档等待目标控件后复查一次。若导航未落地，
  仅在预检阶段、尚无本批草稿或提交标记时，允许在同一扩展重开一次固定入口。
  仍不可读则记录平台、阶段、实际错误和最后核实的身份。只有工具明确报告断连或本地浏览器使用关闭，
  才按该原因报告；不切换到独立 CDP、Playwright 进程、内置浏览器或社媒 API。
- **界面重绘。** 点击后读取新状态，按活动对话框内的角色、名称或可访问标签定位下一步。
  节点失效时丢弃旧索引，重新读取当前页；例如 LinkedIn 动态加载后要重新定位该帖的控制菜单。
  无障碍树信息不足时可用插件截图核对。身份切换、上传或提交回执延迟时先查实际结果。
  文件选择器返回后核对附件名、数量和缩略图；已显示一张正确图片即可继续预览。
- **已进入提交。** 一旦存在 `submission_started_at`，超时、按钮消失、旧索引失效都转入下方
  “结果不明与续跑”，不能据此再点发布。换页或长时间等待后，以当前渠道的编辑器和最近一次
  预览复核作者、受众及附件；无法关联到同一编辑流程时停止。Sheets 按 `reporting.md` 处理。

## Facebook → LinkedIn

每个平台使用以下顺序，Facebook 先执行：

1. 打开固定目标页面的创建帖子操作；不从通用首页发帖。
2. 使用 `facebook.txt` 或 `linkedin.txt`，上传同一临时 JPEG。
3. 确认全部文本、图片和作者身份，核对文案不含网站链接、预览无网站链接卡片，
   处理正常的预览步骤。
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
