# 中国银行美元牌价 · 手机桌面小组件数据源

替代已停止服务的「跨境go」桌面汇率组件。

## 用途

从中国银行官网抓取外汇牌价，输出结构化 JSON，供手机桌面小组件（KWGT 等）直接读取，
实现"在手机桌面一眼看到美元现钞买入价"。

## 数据来源

- 页面：<https://www.boc.cn/sourcedb/whpj/>（中国银行官网外汇牌价）
- 频率：由 GitHub Actions 每 30 分钟自动抓取一次
- 注意：中行牌价随营业时间变动，非交易时段数值保持不变属正常现象

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `boc_rate.py` | 抓取与解析脚本，零第三方依赖，仅用 Python 标准库 |
| `rate.json` | 脚本输出的数据文件，由 GitHub Actions 自动更新，**不要手动编辑** |
| `.github/workflows/update.yml` | 定时任务配置 |

## 手机端使用

数据地址（供小组件读取）：

```
https://ylcdwyyx.github.io/boc-fx/rate.json
```

JSON 结构：

```json
{
  "updated": "2026/09/16 18:58:33",
  "currencies": {
    "usd": {
      "name": "美元",
      "spot_buy": "669.55",
      "cash_buy": "669.55",
      "spot_sell": "672.36",
      "cash_sell": "672.36",
      "mid": "676.28"
    }
  }
}
```

常用取值（KWGT 公式）：

| 含义 | 公式 |
| --- | --- |
| 美元现钞买入价 | `$wg("https://ylcdwyyx.github.io/boc-fx/rate.json", json, .currencies.usd.cash_buy)$` |
| 美元现钞卖出价 | `$wg("https://ylcdwyyx.github.io/boc-fx/rate.json", json, .currencies.usd.cash_sell)$` |
| 牌价时间 | `$wg("https://ylcdwyyx.github.io/boc-fx/rate.json", json, .updated)$` |

## 本地运行

```bash
python boc_rate.py                      # 抓取并写入 rate.json
python boc_rate.py --stdout             # 只打印 JSON
python boc_rate.py --currency 美元 港币  # 只保留指定币种
```

## 支持的币种

`currencies` 字段包含 10 个常用币种（usd/hkd/eur/jpy/gbp/aud/cad/sgd/chf/nzd），
`rates` 字段包含官网全部 45 个币种的完整明细。
