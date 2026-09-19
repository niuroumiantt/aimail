# 能力状态

状态定义(写死,不改):

- ✅ 有测试证明,测试名写在「测试」列,`tools/guard_status.py` 核对它真的存在
- ⚠ 能跑但没测试,或测试不完整
- ⏳ 未完成

没有测试的能力不得标 ✅。

## 能力

| 能力 | 状态 | 测试 |
| --- | --- | --- |
| 守卫:令牌之外禁字面色值 | ✅ | test_hex_outside_tokens_is_caught, test_color_function_outside_tokens_is_caught, test_hex_inside_tokens_is_allowed |
| 守卫:禁 Tailwind 任意值 | ✅ | test_arbitrary_value_is_caught, test_arbitrary_variant_is_caught |
| 守卫:pages/ 只许布局类 | ✅ | test_pages_visual_class_is_caught, test_pages_layout_and_text_size_are_allowed, test_pages_text_color_is_caught_even_with_variant_prefix |
| 守卫:适配器之外禁主机名与别的仓库 | ✅ | test_hostname_outside_backends_is_caught, test_tailnet_ip_outside_backends_is_caught, test_other_repo_name_is_caught, test_hostname_inside_backends_is_allowed |
| 守卫:STATUS 的 ✅ 必须指向真实测试 | ✅ | test_check_without_test_name_is_caught, test_check_naming_missing_test_is_caught, test_check_with_existing_test_passes, test_frontend_test_name_is_found |
| 守卫:抄来的文件必须登记 | ✅ | test_header_without_listing_is_caught, test_listing_without_file_is_caught, test_listed_and_headed_file_passes |
| 守卫:派生表必须有署名字段 | ✅ | test_derived_table_missing_attribution_is_caught, test_nullable_attribution_column_is_caught, test_unmarked_table_is_not_a_derived_table |
| 跳过的测试导致 CI 失败 | ✅ | test_skipped_test_fails_the_run |
| web 工具链:构建、测试、lint 可跑 | ✅ | shell renders the product name |
| 读数卡:四种状态,署名可见,可疑摘要压在警告下并调暗 | ✅ | shows who produced the reading, puts the warning above a summary with unverified numbers and dims it, renders the failure state instead of an empty summary, labels a non-inquiry as such, says plainly when there is no reading yet |
| 主题:亮 / 暗 / 跟随系统,显式选择盖过系统偏好 | ✅ | theme toggle stamps data-theme on the root and clears it for system |
| 头像:同一个人永远同一色,中日韩名取首字 | ✅ | gives the same person the same tint every time, uses the first character for CJK names |
| 空状态:淡铺骨架 + 一句话 + 动作 | ✅ | empty state renders its action |

## 里程碑

| 里程碑 | 状态 |
| --- | --- |
| M0 地基:precommit + 守卫 + CI | ✅ CI 在 PR #2 跑绿 |
| M1 设计系统:令牌、组件库、三页高保真 | ✅ 令牌 + 23 个组件 + /kit + 收件箱/线程/线索,亮暗截图在 docs/design/;数据是编的样本,真数据 M2 |
| M2 收信:IMAP 进来,原文落库 | ⏳ |
| M3 读信:摘要 + 核对 + 评测集 | ⏳ |
| M4 线索:建议 → 人确认 → 事实 | ⏳ |
| M5 草稿:人改人发 | ⏳ |
| M6 记忆:同一客户的历史进上下文 | ⏳ |
| M7 附件:BOM 进摘要 | ⏳ |
| M8 下游:lead API 与 webhook | ⏳ |
| M9 第二个邮箱 | ⏳ |
