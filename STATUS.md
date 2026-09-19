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
| 线索:询盘读数后自动提建议、带署名;提取失败也记录、可数 | ✅ | test_inquiry_reading_creates_an_open_suggestion_with_attribution, test_non_inquiry_creates_no_suggestion, test_failed_extraction_is_recorded_not_silent, test_unverified_numbers_in_a_suggestion_are_kept |
| 线索:只有人能把建议变成事实,后台没有这条路 | ✅ | test_confirm_requires_a_person, test_background_code_has_no_way_to_confirm, test_api_refuses_confirm_without_identity_and_accepts_tailscale_header |
| 线索:确认 → 线索表 + 线程归待报价;不能确认两次;忽略不产生线索;状态受校验 | ✅ | test_confirm_turns_suggestion_into_a_lead_and_moves_the_thread, test_confirming_twice_is_rejected, test_dismiss_marks_the_suggestion_and_creates_no_lead, test_lead_status_is_validated |
| API:建议与线索的形状与界面一致 | ✅ | test_api_suggestion_and_lead_shapes_match_the_web |
| 界面:确认前先写名字;建议里的可疑数字先标出;提取失败有计数 | ✅ | asks for a name before anyone can confirm, does not ask for a name once there is one, shows unverified numbers on a suggestion before confirmation, counts inquiries whose lead extraction failed |
| 发信:没有令牌发不出;令牌只签给人、绑线程、一次性、十分钟过期 | ✅ | test_token_is_bound_and_single_use, test_expired_token_is_rejected, test_token_is_only_minted_for_a_person, test_send_without_a_token_is_impossible |
| 发信:回信归客户线程、带 In-Reply-To、落库为我方、线程归已回复;空信拒发 | ✅ | test_sent_message_threads_correctly_and_lands_as_outgoing, test_empty_body_or_no_recipient_is_refused |
| 发信:收信、读数、起草模块连发信模块都 import 不到 | ✅ | test_background_modules_never_import_send |
| 起草:以整条线程为依据,带署名落库,失败也落库且显形 | ✅ | test_draft_is_stored_with_attribution, test_failed_draft_is_visible_not_blank, test_draft_source_is_the_whole_thread |
| API:发信要人、要令牌、要 SMTP;伪造令牌 403;令牌用一次作废;起草要人 | ✅ | test_api_send_flow_requires_person_token_and_transport, test_api_draft_endpoints |
| 记忆:同一地址或同一公司域算同一位客户,公共邮箱域只认地址;不出本邮箱,不含自己 | ✅ | test_same_address_is_the_same_customer, test_same_company_domain_is_the_same_customer, test_public_mail_domain_is_not_a_company, test_history_excludes_itself_and_other_mailboxes |
| 记忆:历史段只有原文摘录与我们记的状态,模型输出进不去;历史里的数字算回得到原文;没有历史不占提示词 | ✅ | test_history_is_raw_excerpt_and_our_status_never_a_model_summary, test_numbers_from_history_count_as_verified, test_no_history_adds_nothing_to_the_prompt |
| 记忆:读数与起草的模型输入都带这位客户的往来;详情 API 带 history,列表不带 | ✅ | test_reader_shows_the_model_this_customers_history, test_draft_source_carries_history, test_thread_detail_carries_history_in_the_web_shape |
| 界面:线程页从详情接口取信件与历史;老客户显示往来卡,可点回去;第一次来信在页头标出 | ✅ | thread page shows the messages from the detail which the list does not carry, shows past dealings with their outcome and a way back to them, marks a first-time customer in the thread header, says nothing about history until the detail has loaded, shows the history card for a returning customer |
| 附件:PDF 文字层、xlsx、docx、csv/txt 读成文字;扫描件、图片、坏文件、超大文件都是带原因的失败,不留白 | ✅ | test_pdf_text_layer_is_read, test_scanned_pdf_is_failed_with_a_visible_reason, test_xlsx_rows_become_tab_separated_lines, test_docx_paragraphs_are_read, test_image_unknown_and_broken_files_fail_with_reasons_not_blanks, test_oversized_attachment_is_refused_before_parsing, test_text_files_decode_utf8_then_gb18030 |
| 附件:读出的文字带署名落库、幂等,原字节不动;读不出不挡收信 | ✅ | test_ingest_stores_attachment_text_with_attribution_and_keeps_the_blob, test_broken_attachment_does_not_block_ingest |
| 附件:读数与起草的模型输入带附件文字,附件里的数字算回得到原文;API 按邮箱隔离按需取正文 | ✅ | test_reader_sees_attachment_text_and_its_numbers_verify, test_draft_source_carries_attachment_text, test_api_exposes_attachment_state_and_text_only_within_the_mailbox |
| 界面:附件片标出读没读出来、原因可见;点开看读出的文字;没有取用器时只列名字 | ✅ | marks an attachment that could not be read and says why, opens the text that was read out of an attachment, shows the reason instead of a blank sheet when the text is missing, lists attachments without a way to open them when no handler is given |
| 下游:/v1 只认机器令牌;只出确认过的事实,建议不出门;形状钉死;机器令牌写不了线索 | ✅ | test_v1_leads_requires_a_machine_token, test_v1_returns_only_confirmed_facts_never_suggestions, test_machine_token_cannot_confirm_or_edit_leads, test_token_parsing_rejects_short_or_nameless_tokens |
| 下游:游标 (since, after) 同一秒不漏;按状态过滤;按邮箱隔离;CSV 导出 | ✅ | test_v1_since_cursor_status_filter_and_mailbox_isolation, test_csv_export_has_one_row_per_lead_and_survives_commas |
| 推送:写线索的同一事务里记事件;签名可验;送到即标记不重复;失败退避重试、原因可见、永不丢 | ✅ | test_confirm_and_update_enqueue_events_atomically, test_delivery_is_signed_and_marked_delivered, test_failed_delivery_backs_off_and_stays_visible, test_network_error_is_a_recorded_failure_not_a_crash, test_real_http_delivery_end_to_end |
| 下游:一个外部脚本只凭令牌走 HTTP 拿到确认过的线索 | ✅ | test_pull_leads_script_gets_confirmed_leads_over_http_with_only_a_token |
| 界面:推送没送到在线索页显形;导出 CSV | ✅ | shows undelivered pushes so nobody assumes the OA got them, says nothing about pushes when no webhook is configured or all went through, offers the CSV export of confirmed leads |
| 界面:回信框——占位没换发不出;署名、可疑数字、追问先看见;失败不留白;只经人发;草稿可找回 | ✅ | refuses to send while the name placeholder is still in the body, shows who drafted and which numbers are unverified before anyone sends, shows the failure instead of an empty draft, sends only what the person wrote through their handler and then closes, keeps the composer open and shows the reason when the server refuses, asks for a name before drafting or sending, restores the latest stored draft when reopened, decides the hard rules in code before anything reaches the server |

## 里程碑

| 里程碑 | 状态 |
| --- | --- |
| M0 地基:precommit + 守卫 + CI | ✅ CI 在 PR #2 跑绿 |
| M1 设计系统:令牌、组件库、三页高保真 | ✅ 令牌 + 23 个组件 + /kit + 收件箱/线程/线索,亮暗截图在 docs/design/;数据是编的样本,真数据 M2 |
| M2 收信:IMAP 进来,原文落库 | ⚠ 代码与测试齐;对真邮箱的首次收信要在部署机上验,验完改 ✅ |
| M3 读信:摘要 + 核对 + 评测集 | ⚠ 代码、测试、评测脚本齐;Spark 上的真实分数要在部署机跑 evals/summarize_inquiry/run.py,跑完把数填进这里再改 ✅ |
| M4 线索:建议 → 人确认 → 事实 | ⚠ 代码、测试齐;Spark 上 extract_lead 的真实分数要在部署机跑 evals/extract_lead/run.py |
| M5 草稿:人改人发 | ⚠ 代码、测试齐;真 SMTP 的第一封要在部署机上发给自己验;Spark 上 draft_reply 的真实分数要跑 evals/draft_reply/run.py |
| M6 记忆:同一客户的历史进上下文 | ⚠ 代码、测试齐;「只有一句新内容」的样本要在 Spark 上跑 evals/summarize_inquiry/run.py 看摘要是否指回历史里的型号 |
| M7 附件:BOM 进摘要 | ⚠ PDF 文字层 / xlsx / docx / csv 已进摘要与草稿,代码、测试齐;扫描件与图片的 vision 路由**推迟**(等手里有真实扫描件再接,界面已把它们标为「没读出来」);「正文只说 see attached」的样本要在 Spark 上跑评测 |
| M8 下游:lead API 与 webhook | ✅ /v1/leads(令牌、游标、CSV)与签名推送有端到端测试(真起服务、真走 HTTP);OA 那头的接收端不在本仓库,接上后按 docs/api/v1.md 验签即可 |
| M9 第二个邮箱 | ⏳ |
