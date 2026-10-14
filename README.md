# 万川社媒自动发布 · Wanchuan Social Publisher

用于 Codex 的万川 Vantrend Beauty 社媒发布技能。从官网产品库随机选品或使用指定产品，生成英文文案和产品四宫格图片，依次发布到 Facebook、LinkedIn，并回读核验 Google Sheets 发布记录。

## 功能与范围

- 遍历官网完整产品分页池；随机任务最多审核 10 个候选，保存选品及跳过原因。
- 仅采用产品专属、无冲突的事实；分别生成 Facebook 和 LinkedIn 英文文案。
- 使用 Codex 内置图片生成能力，以产品主图为参考制作一张正方形四宫格图片。
- 校验账号身份、素材、文案、文件哈希和发布预览；提交后核验真实帖子链接。
- 使用运行 manifest 保存进度；已成功渠道不重发，结果不明时先核对平台状态。
- 两个平台成功后向既定表格追加一条五列记录，回读并检查重复。
- 支持仅生成本地素材的 `dry-run`，以及用户明确指定的失败续跑。

不含站内文章、网站发布 API 或自动创建定时任务。

## 固定目标

| 项目 | 目标 |
| --- | --- |
| 产品库 | [vantrendtools.com/products](https://www.vantrendtools.com/products/) |
| Facebook | [万川主页 · 61575467138674](https://www.facebook.com/profile.php?id=61575467138674) |
| LinkedIn | [万川公司主页管理入口 · 146727123](https://www.linkedin.com/company/146727123/admin/dashboard/) |
| 发布记录 | 既有 `social-auto-upload` Google Sheet，详见[记录规范](wanchuan-social-publisher/references/reporting.md) |
| 时区 | Asia/Shanghai |

这是万川专用技能，目标账号和记录表已固定。仓库不提供账号登录状态、密钥或授权；执行者须具备相应账号和记录表的权限。若用于其他品牌，须同步调整技能说明、参考文档、脚本中的身份及表格配置，并重新验证。

## 安装

下载并解压 [wanchuan-social-publisher.zip](wanchuan-social-publisher.zip)，将其中的 `wanchuan-social-publisher` 文件夹放入自己的 Codex 技能目录（通常为 `~/.codex/skills/`）。也可以克隆仓库后复制同名文件夹。保留文件夹内部结构，确保 `scripts/` 与 `SKILL.md` 同级。

运行脚本需要 Python 3 和 Pillow。安装 Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

完整发布由 Codex 协调，需要可用的内置图片生成能力、受支持的浏览器工具或社媒连接器，以及 Google Sheets 连接器。Python 脚本负责采集、图片优化、本地校验和状态记录，不会自行登录或提交社媒帖子。

## 在 Codex 中使用

```text
使用 $wanchuan-social-publisher 运行一次。
```

```text
使用 $wanchuan-social-publisher 做一次 dry-run，仅生成文案和图片，不发布。
```

```text
使用 $wanchuan-social-publisher 推广这个官网产品：<产品详情页 URL>
```

```text
使用 $wanchuan-social-publisher 续跑 <运行目录>，保留原产品和素材，跳过已成功渠道。
```

明确要求执行 live 发布时，完成预检后直接发布。登录、MFA、验证码、账号身份不明或权限缺失时停止。仅讨论、创建或修改技能不等于执行发布。普通的新执行创建新运行目录；续跑须明确指定。

## 文件结构

```text
wanchuan-social-publisher/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── content-spec.md
│   ├── product-selection.md
│   ├── publishing.md
│   └── reporting.md
└── scripts/
    ├── scrape_product.py
    ├── content_plan.py
    ├── optimize_image.py
    ├── validate_campaign.py
    ├── update_manifest.py
    ├── validate_completion.py
    └── test_workflow.py
```

运行产物默认写入当前工作目录的 `campaign-runs/`，包括文案、图片、manifest 和证据。此仓库仅分发技能；本地运行产物、社媒截图、表格回读内容和浏览器状态不纳入版本控制。

## 验证

以下离线测试不访问或发布到外部服务：

```bash
python3 wanchuan-social-publisher/scripts/test_workflow.py
```

发布前运行 `validate_campaign.py`，双平台及表格回读完成后运行 `validate_completion.py`。命令参数和证据格式见 [SKILL.md](wanchuan-social-publisher/SKILL.md)。

2026-10-14 的本地验收完成了一组万川 Facebook、LinkedIn 发布与表格回读核验。平台界面、权限和产品事实仍须在每次执行时重新检查。
