# weak top5 剩余负例诊断
## 口径
基于当前 runtime 的 weak PASS+WATCH 实际每日 top5，不重新排序；收益标签来自 PostgreSQL 日线。
## 当前 top5
- top3：ret3>=5 21/72，ret3<=0 40/72，ret3_mean -0.011。
- top5：ret3>=5 30/120，ret3<=0 68/120，ret3_mean -0.5152。
## 结论
- 实际 top5 剩余负例没有出现足够大的单一干净负例组；多数高频组同时包含较多 ret3>=5 正例。
- B3 upper/near_high + above_hold + bull_stack + tight + normal + rising 在 top5 中负例多，但全量同组仍有 23/110 个 ret3>=5，粗扣会误伤。
- 最干净的窄风险组是 B2 extended + expanding + repair_from_low + green MACD + price_turnover_rise，但全量只有 5 个样本，只适合继续观察或极小 top5 风险扣分候选。
- BBI/BIAS/OBV 在剩余 top5 负例中没有形成独立 veto；high_positive bias 甚至在 B2 above_hold 子集里均值偏正，不能作为扣分条件。
## 高频负例组合
- `B3|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising|hist=red_expanding|turnover=price_up_turnover_not`：top5 负例 3 个，负例均值 -7.1528；全量同组 n=9、ret3>0=5、ret3>=5=2、ret3<=0=4、均值 -0.2644。
- `B2|trend_start|price=extended_or_unknown|midline=above_hold|support=bull_stack|compression=tight|volume=expanding|kdj=repair_from_low|hist=green_or_zero|turnover=price_turnover_rise`：top5 负例 2 个，负例均值 -4.5791；全量同组 n=5、ret3>0=1、ret3>=5=0、ret3<=0=4、均值 -4.042。
- `B2|trend_start|price=extended_or_unknown|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=low|hist=green_or_zero|turnover=price_turnover_rise`：top5 负例 2 个，负例均值 -5.9486；全量同组 n=11、ret3>0=4、ret3>=5=3、ret3<=0=7、均值 -2.3982。
- `B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral|hist=green_or_zero|turnover=price_turnover_rise`：top5 负例 2 个，负例均值 -3.6604；全量同组 n=40、ret3>0=15、ret3>=5=5、ret3<=0=25、均值 -1.5493。
- `B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral|hist=red_expanding|turnover=price_turnover_rise`：top5 负例 2 个，负例均值 -6.7301；全量同组 n=18、ret3>0=7、ret3>=5=5、ret3<=0=11、均值 -0.0367。
- `B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=low|hist=green_or_zero|turnover=price_turnover_rise`：top5 负例 2 个，负例均值 -5.6969；全量同组 n=27、ret3>0=13、ret3>=5=7、ret3<=0=14、均值 -0.8833。
## 候选风险条件
- `b2_extended_expanding_repair_green_turnover_rise`：全量 n=5、ret3>0=1、ret3>=5=0、ret3<=0=4、均值 -4.042；top5 n=2、ret3>=5=0、ret3<=0=2、均值 -4.5791。
- `b2_extended_normal_low_green_turnover_rise`：全量 n=11、ret3>0=4、ret3>=5=3、ret3<=0=7、均值 -2.3982；top5 n=3、ret3>=5=0、ret3<=0=2、均值 -3.6599。
- `b2_upper_normal_neutral_green_turnover_rise`：全量 n=47、ret3>0=22、ret3>=5=5、ret3<=0=25、均值 -0.9864；top5 n=2、ret3>=5=0、ret3<=0=2、均值 -3.6604。
- `b3_upper_turnover_mixed_or_not`：全量 n=203、ret3>0=88、ret3>=5=38、ret3<=0=115、均值 -0.7519；top5 n=29、ret3>=5=6、ret3<=0=19、均值 -2.8575。
- `b3_trend_upper_normal_rising_red_no_turnover_confirm`：全量 n=15、ret3>0=8、ret3>=5=4、ret3<=0=7、均值 0.3467；top5 n=6、ret3>=5=1、ret3<=0=4、均值 -4.1357。
- `b3_rebound_upper_normal_rising_green`：全量 n=31、ret3>0=11、ret3>=5=3、ret3<=0=20、均值 -2.3997；top5 n=1、ret3>=5=0、ret3<=0=1、均值 -7.7257。
## 建议
- production_change：暂不追加 weak top5 生产扣分；当前剩余负例以混杂组为主，继续扣分更容易牺牲 ret3>=5 捕捉。
- watchlist：保留 b2_extended_expanding_repair_green_turnover_rise 和 b2_extended_normal_low_green_turnover_rise 为后续样本扩展后的 top5-only 风险观察。
- boundary：不改 PASS/WATCH verdict，不做 broad B3 或 broad B2 upper 扣分。
