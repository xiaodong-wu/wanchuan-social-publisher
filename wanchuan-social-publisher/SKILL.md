---
name: wanchuan-social-publisher
description: 为万川 Vantrend Beauty 从 vantrendtools.com/products/ 随机或指定选品，生成英文 Facebook、LinkedIn 文案和产品四宫格图片，发布到固定万川账号并记录结果。适用于万川社媒自动发布、指定产品推广、dry-run 和明确的失败续跑；不含站内文章或网站发布 API。
---

# 万川社媒自动发布

参考 sswyauto-product-publisher，为万川独立维护的双社媒发布流程。
用户明确要求执行本技能或发布时，完成预检后直接发布，无需中途再次确认。
仅讨论、创建、修改、审查技能不授权执行发布。`dry-run` 仅生成本地草稿和素材，
不提交帖子、不写在线表格。新触发启动新任务；明确续跑才恢复旧任务。

## 固定配置

| 项目 | 固定值 |
|---|---|
| 品牌 | 万川 / Vantrend Beauty |
| 产品库 | https://www.vantrendtools.com/products/ |
| Facebook | https://www.facebook.com/profile.php?id=61575467138674 |
| Facebook Page ID | `61575467138674` |
| LinkedIn | https://www.linkedin.com/company/146727123/admin/dashboard/ |
| LinkedIn Company ID | `146727123` |
| 时区 | Asia/Shanghai |
| 发布顺序 | Facebook → LinkedIn → Google Sheets 记录 |

不创建站内新闻、新闻封面、文章配图或 SEO 长文；不需要网站 API 密钥，不调用网站写入接口。
两条社媒文案均链接所选产品页。禁止使用其他品牌账号、旧技能账号或个人身份代发。
本技能不自行创建定时任务；仅在用户另行指定周期时设置调度。

## 执行流程

1. **预检。** 读取 [发布流程](references/publishing.md)。先查询可用发布连接器，
   无合适连接器时使用当前支持的浏览器工具和已登录 Chrome。读取工具初始化文档，
   不调用过时浏览器接口。确认两个固定账号均有发帖权限；Facebook 可执行一次已明确
   指向目标主页的两步身份切换。登录、MFA、验证码、身份不明或权限缺失时停止，
   在生成素材前报告阻塞。dry-run 不要求社媒登录。
2. **选品。** 读取 [选品规则](references/product-selection.md)。执行
   `scripts/scrape_product.py --mode live --output-root RUNS_ROOT`；dry-run 改用
   `--mode dry-run`。默认输出当前工作目录的 `campaign-runs/`，不得存入技能目录。
   指定产品加 `--product-url URL`。随机任务遍历完整分页池后打乱，最多审核十个候选。
   保留 `catalog.json`、`selection.json`，使用返回的唯一运行目录和 manifest。
3. **审核和文案。** 读取 [内容与图片规范](references/content-spec.md)，检查保存的产品
   HTML、`product.json`、`content-plan.json` 和 `source/hero.*`。必须用 `view_image`
   查看主图。只使用产品专属且无冲突的事实，不把分类页、评论、FAQ、通用工厂文案
   当作该产品的能力证据。保存 `facebook.txt` 和 `linkedin.txt`。
4. **图片。** 加载当前安装的 `imagegen` 技能，使用 Codex 内置图片生成工具，以主图
   作为身份参考生成一张正方形四宫格图。遵循内容规范的有界修正流程。将实际生成文件
   复制到运行目录后，执行 `scripts/optimize_image.py INPUT RUN_DIR/social.webp --kind social
   --transport-jpeg RUN_DIR/social-upload.jpg`。规范资产为无元数据 WebP；社媒上传使用
   临时 JPEG。无需创建其他图片。
5. **全批次校验。** 按内容规范完成 `evidence/review.json`，包含源事实、文案和图片
   审核及最终文件 SHA-256。执行 `scripts/validate_campaign.py MANIFEST`。修改已审核
   文件后重新检查并更新相应审核。全部通过才可发布；dry-run 在此结束并报告草稿路径。
6. **双平台发布。** 遵循发布流程，在每个平台最终提交前记录
   `scripts/update_manifest.py MANIFEST --channel facebook|linkedin --status pending --submission-started`。
   核对预览、身份、文案和图片后仅提交一次。查看实际发布列表与帖子页面，保存核验记录、
   公开帖子链接和发布身份，再记录 `published`。结果不明先核对，禁止猜测重发。
7. **报告。** 两条帖子核验成功后立即按 [记录规范](references/reporting.md) 写入并
   回读原 `social-auto-upload` 表的一条五列表格记录。C 列使用 `不适用（仅社媒）`，
   不伪造站内文章链接。执行 `scripts/validate_completion.py MANIFEST` 通过后才能
   报告完整成功。表格失败仅续跑记录，不重发帖子。双平台成功后可删除临时上传 JPEG；
   保留规范图片、审核记录和 SHA-256。

## 失败与续跑

- 只有产品专属证据问题允许提交前换品，沿用同一十次候选预算；网络、工具、权限或
  文件系统故障应停止。生成文案或图片出错在同一产品上修正，不用换品绕过。
- 任何提交开始后不换品，包含提交结果不确定、一个平台成功另一个失败的情况。
  状态更新不得抹除 `submission_started_at`、历史或成功链接。
- 用户指定运行目录、要求续跑最新未完成任务，或明确修复刚报告的阻塞并重试时，
  才恢复旧 manifest。重查当前账号状态，跳过已发布平台；不要用新任务重置失败历史。
- 新的正常执行随机选一个产品，历史产品可重复。每次至多发布一组双平台帖子。
- 最终以中文报告产品和链接、已审核/跳过候选数量及原因、两个平台的准确状态和
  帖子链接、表格记录状态和链接、本地运行目录及选品台账。dry-run 不能称为已发布。

## 脚本

脚本路径相对于本技能目录。使用 Python 3.9+ 和 Pillow；网络采集使用 Python 标准库。

```bash
python3 scripts/scrape_product.py --mode live --output-root RUNS_ROOT
python3 scripts/scrape_product.py --mode dry-run --product-url PRODUCT_URL --output-root RUNS_ROOT
python3 scripts/scrape_product.py --retry-from MANIFEST --reason "具体产品证据问题"
python3 scripts/optimize_image.py INPUT OUTPUT --kind social --transport-jpeg UPLOAD_JPEG
python3 scripts/validate_campaign.py MANIFEST
python3 scripts/update_manifest.py MANIFEST --channel facebook --status pending --submission-started
python3 scripts/update_manifest.py MANIFEST --channel facebook --status published --url POST_URL --identity-id 61575467138674 --evidence EVIDENCE_FILE
python3 scripts/update_manifest.py MANIFEST --channel linkedin --status published --url POST_URL --identity-id 146727123 --evidence EVIDENCE_FILE
python3 scripts/validate_completion.py MANIFEST --row-only
python3 scripts/update_manifest.py MANIFEST --channel google_sheet --status reported --url SHEET_URL --external-id ROW_NUMBER --evidence READBACK_FILE --values-file VALUES_JSON
python3 scripts/validate_completion.py MANIFEST
```

`--mode` 默认 `dry-run`。恢复任务沿用原模式，不把已完成 dry-run 修改成 live；若用户
要求随后发布，创建明确的 live 运行，重新核验账号和素材。脚本只处理公开读取、本地素材
和状态；真正发帖及 Sheets 写入由当前授权的连接器或浏览器完成。
