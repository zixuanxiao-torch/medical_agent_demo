# 新数据清洗后并入知识库（JSONL 合并 + 增量建库）

`shuju.ipynb` 仍是完整清洗流水线：原始 txt → `2out` → `2out2` → `2out3/kb.jsonl` → `2out4/kb_clean.jsonl`（及脱敏检查）。  
**每来一批新导出数据**：把 notebook 里各轮的 `IN_DIR` / 输出目录改成新批次路径，跑通后得到**新的** `kb_clean.jsonl`。

与已有知识库合并时，**不要手抄进旧文件**，用脚本按与 `kb_store._stable_id` 相同规则去重后写出新文件，再增量写入 Chroma。

## 1）合并 JSONL

```powershell
cd C:\Users\10409\Documents\work\shixi_agent\medical_agent_demo
py -3 -m scripts.kb_merge_jsonl --base "D:\shixi_agent\黄剑企业微信导出\out4\kb_clean.jsonl" --add "D:\shixi_agent\黄剑企业微信导出\新批次\2out4\kb_clean.jsonl" --out "D:\shixi_agent\黄剑企业微信导出\out4\kb_clean_merged.jsonl"
```

说明：

- `--base`：当前线上/正在用的总库 JSONL。
- `--add`：本批 notebook 产出的 `kb_clean.jsonl`。
- 同一 `hash` 或同一 `question+answer`（MD5）在 base 里已存在时，**add 里重复条会被丢弃**（保留 base 先出现的版本）。

## 2）切换 `.env` 中的源文件（二选一）

- 把 `KB_SOURCE_JSONL` 改成合并后的路径，例如 `...kb_clean_merged.jsonl`；或  
- 将 `kb_clean_merged.jsonl` **覆盖备份后**替换原 `kb_clean.jsonl`，保持 `.env` 不变。

## 3）增量写入 Chroma

```powershell
py -3 -m scripts.kb_build_chroma
```

默认即为增量：已存在的 id 会跳过，只对新行算 embedding 并 upsert。

进度说明：增量阶段会长时间「只跳过、不新增」，脚本会按 `--progress-scan-every`（默认每 **2000** 条已扫描 JSONL 记录）打印 `scan_progress`，避免误以为卡住；仍可用 `--progress-every` 控制「每新增多少条」打印 `upserted`。

本机终端想强制无缓冲可设：`$env:PYTHONUNBUFFERED=1` 后再运行。

全量重建（慎用）：

```powershell
py -3 -m scripts.kb_build_chroma --rebuild
```

## 4）验收

- 脚本合并结束会打印 `out_total`、重复条数等统计。
- 建库结束会打印 `added` / `skipped` / `count`。
- 服务侧 `/chat` 开 `debug` 看是否仍出现 `kb_retrieve`。
