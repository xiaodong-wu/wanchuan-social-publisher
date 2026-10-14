# 全量选品与候选替换

从 `https://www.vantrendtools.com/products/` 开始，遍历全部同站产品分页。
`/products/`、`/products/index.html` 和 `/products/1.html` 归一为同一首页。
只收录产品卡片中的详情链接，不把导航、新闻、页脚或分类页混入产品池。
完整遍历并按 URL 去重后才打乱，保留全部分页和来源记录；十次上限约束候选产品，
不限制分页数。分页 404/410 单独记录，其他目录网络故障停止，不用不完整产品池继续。

每次运行有一个 `selection.json` 台账；候选失败记录原因和产品证据。默认最多十个，
指定产品默认只审核该产品。仅用户明确允许替代指定产品时加 `--allow-reselect`。
不可重开台账逃避上限。产品可在以后的独立运行重复。

抓取器依照万川实际页面结构读取：

- `page_content_box` 中 `item_box` 产品卡片及 `products` 分页；
- `product_info` 的标题、`product_info_description` 简介；
- `product_attributes` 快速参数、`product_specifications` 表格；
- `show_item_box7` 产品专属说明；
- `product_gallery_main` 主图。

主图须可解码且短边不少于 300 像素，产品至少有三个可用规格。元描述、图片 alt、
客户评论及通用工厂信息不会用来补齐参数。页面模板变化导致解析不足时先检查原始 HTML；
不要将目录、工具或网络故障误称为十个产品同时不合格。

脚本只筛查结构化冲突与 VC 系列混合型号。必须人工比较正文与表格、核对主图及
应用条件。无冲突并不意味着所有提取文字都适合宣传。

若人工发现问题且尚未提交任何渠道：

```bash
python3 scripts/scrape_product.py --retry-from MANIFEST --reason "具体冲突及来源"
```

新候选使用同一台账剩余预算和原 live/dry-run 模式，创建独立运行目录；全部文案、
图片和审核重新制作。已进入任何提交状态，包括结果不明的点击或已成功帖子，禁止换品。
不以网络、权限、图像生成或文案格式问题换品。
