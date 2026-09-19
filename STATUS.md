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
| 收信:原文落库后不可改不可删(数据库触发器) | ✅ | test_message_update_is_rejected, test_message_delete_is_rejected, test_attachment_is_immutable, test_raw_bytes_are_kept_verbatim |
| 收信:重复投递只存一次(Message-ID + 原文哈希两道唯一约束) | ✅ | test_same_message_id_is_stored_once, test_same_bytes_are_stored_once_even_without_message_id, test_redelivered_message_is_skipped_not_duplicated |
| 收信:断点续拉,UIDVALIDITY 变化不重复 | ✅ | test_cursor_advances_per_message_so_a_crash_resumes, test_uidvalidity_change_refetches_without_duplicating, test_second_run_fetches_nothing_new |
| 收信:解析失败不丢原文 | ✅ | test_unparsable_message_keeps_its_raw_bytes, test_garbage_bytes_do_not_crash_the_parser |
| 解析:HTML 退化成文本、附件带哈希、编码主题、线程头 | ✅ | test_plain_text_body_and_headers, test_html_only_mail_falls_back_to_text, test_attachments_are_listed_with_hash, test_thread_headers_are_parsed |
| 切引用:Gmail / Outlook / 中文客户端 / > 行,认不出整封算新增 | ✅ | test_gmail_on_wrote_splits, test_outlook_from_sent_block_splits, test_chinese_reply_marker_splits, test_angle_bracket_lines_split, test_no_quote_keeps_everything_as_new |
| 归并:靠头、靠主题+对方、不同对方不并、超 60 天不并、我方回信归客户线程 | ✅ | test_reply_with_in_reply_to_joins_thread, test_same_subject_same_sender_joins_thread, test_same_subject_different_sender_is_a_new_thread, test_same_subject_after_window_is_a_new_thread, test_outgoing_reply_joins_customer_thread |
| IMAP 连接校验证书与主机名 | ✅ | test_ssl_context_verifies_certificate_and_hostname |
| API:线程列表与详情形状与界面一致,错 ID 404 | ✅ | test_thread_list_has_the_web_shape, test_thread_detail_carries_messages_quoted_and_attachments, test_unknown_thread_is_404, test_folder_filter |
| 守卫:没有评测集的模型任务不上线 | ✅ | test_task_without_eval_folder_is_caught, test_task_with_run_but_no_sample_dataset_is_caught, test_task_with_complete_eval_folder_passes, test_module_without_task_version_needs_no_evals |
| 后端:模型不合规时报错、只重试一次、绝不编结果 | ✅ | test_truncated_json_is_rejected_rather_than_guessed, test_bad_output_gets_exactly_one_repair_attempt, test_wrong_types_are_rejected_not_coerced, test_unknown_backend_name_is_rejected_loudly |
| 后端:发给网关的字节正确(路径、Bearer、模型名、温度 0、字段模板) | ✅ | test_request_lands_on_the_openai_chat_completions_path, test_api_key_is_sent_as_a_bearer_token, test_payload_carries_model_zero_temperature_and_shape, test_fenced_answer_from_a_real_socket_is_parsed |
| 核对:模型引用的数字回原文核对,千分位不误判 | ✅ | test_number_absent_from_source_is_flagged, test_thousands_separator_is_not_a_hallucination, test_chinese_comma_and_whitespace_normalized |
| 读数:落库带署名,失败也落库且显形,不是询盘归 invalid | ✅ | test_reading_is_stored_with_attribution, test_failed_reading_is_stored_as_failed_not_empty, test_non_inquiry_moves_thread_to_invalid, test_unverified_numbers_are_recorded_not_hidden |
| 读数:核对依据与模型输入是同一份文本;只读来信;读数失败不挡收信 | ✅ | test_quoted_history_is_part_of_the_verified_source, test_ingest_reads_incoming_only, test_reader_failure_does_not_block_ingest |
| API:读数以界面形状暴露 | ✅ | test_api_exposes_reading_in_the_web_shape |

## 里程碑

| 里程碑 | 状态 |
| --- | --- |
| M0 地基:precommit + 守卫 + CI | ✅ CI 在 PR #2 跑绿 |
| M1 设计系统:令牌、组件库、三页高保真 | ✅ 令牌 + 23 个组件 + /kit + 收件箱/线程/线索,亮暗截图在 docs/design/;数据是编的样本,真数据 M2 |
| M2 收信:IMAP 进来,原文落库 | ⚠ 代码与测试齐;对真邮箱的首次收信要在部署机上验,验完改 ✅ |
| M3 读信:摘要 + 核对 + 评测集 | ⚠ 代码、测试、评测脚本齐;Spark 上的真实分数要在部署机跑 evals/summarize_inquiry/run.py,跑完把数填进这里再改 ✅ |
| M4 线索:建议 → 人确认 → 事实 | ⏳ |
| M5 草稿:人改人发 | ⏳ |
| M6 记忆:同一客户的历史进上下文 | ⏳ |
| M7 附件:BOM 进摘要 | ⏳ |
| M8 下游:lead API 与 webhook | ⏳ |
| M9 第二个邮箱 | ⏳ |
