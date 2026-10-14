# 仅社媒任务的 Google Sheets 记录

沿用参考技能的 `social-auto-upload` 表。明确执行本技能的 live 发布包含发布后的这一条
审计记录；不等待另一个品牌任务，不拼接不同域名。只在 Facebook 和 LinkedIn 两条
帖子均已核验后追加。部分失败、阻塞及 dry-run 仅记录本地，不写线上表。

使用前加载 `google-drive:google-sheets`。即时读取元数据和表头，核对：

- [social-auto-upload](https://docs.google.com/spreadsheets/d/18iLpJ7bpDbJzxYtg0vsSOQxOR2e0KBuMI9C7LK0MhAw/edit)
- Spreadsheet ID：`18iLpJ7bpDbJzxYtg0vsSOQxOR2e0KBuMI9C7LK0MhAw`
- Sheet：`工作表1`；使用即时读取到的 sheetId，不硬编码猜测。
- `A1:E1`：`域名`、`发布时间`、`发布的站内链接`、`Facebook链接`、`LinkedIn链接`。

恰好五个字符串：

1. `vantrendtools.com`
2. 双平台中较晚的首次核验时间，Asia/Shanghai，`YYYY-MM-DD HH:mm:ss`
3. `不适用（仅社媒）`
4. 已核验 Facebook 永久链接
5. 已核验 LinkedIn 永久链接

C 列明确说明没有站内文章，不把产品页冒充本次发布的站内文章。不要修改表头、扩列、
创建替代表或写其他品牌的行。表头不一致或无法按既有权限写入时记录 `blocked`。

## 幂等步骤

1. `python3 scripts/validate_completion.py MANIFEST --row-only` 生成稳定的五个值，保存为
   `evidence/sheet-values.json`。脚本要求两个实际社媒帖子都已核验。
2. 在表的实际使用范围内以分段有限范围搜索 D:E，分别找 Facebook 和 LinkedIn 精确链接。
   完整扫描已用行；范围截断或结果未穷尽不能视为“未找到”。不以产品 URL 去重，因为
   新任务可以推广同一产品；不以 C 列固定占位文本去重。
3. 两条链接在同一唯一行且五值完全一致：直接回读验证，作为已有记录，不再追加。
4. 任一链接出现在不同行、重复行或值冲突：记录 `blocked`，不要覆盖或再追加。
5. 确认两条链接均不存在后追加一条五列记录，立即回读并确认恰好一行完全匹配。
6. 保存真实回读内容到 `evidence/sheet-readback.json`，字段为 `spreadsheet_id`、`row`、
   `values`（回读的五值数组）、`matching_rows`（确认唯一时为 1），可额外保存工具原始输出。
   不要仅复制预期值充当回读。记录状态：

```bash
python3 scripts/update_manifest.py MANIFEST --channel google_sheet --status reported \
  --url 'https://docs.google.com/spreadsheets/d/18iLpJ7bpDbJzxYtg0vsSOQxOR2e0KBuMI9C7LK0MhAw/edit' \
  --external-id ROW_NUMBER --evidence RUN_DIR/evidence/sheet-readback.json \
  --values-file RUN_DIR/evidence/sheet-values.json
python3 scripts/validate_completion.py MANIFEST
```

如果追加结果不明，重新搜索精确社媒链接并回读，绝不直接重复追加。时间取 manifest
已有核验时间，不用每次重试的当前时间，避免已存在记录因时间变化被误判冲突。
表格失败不会撤回或重发成功帖子；最终区分“帖子已发布”与“记录未完成”。
