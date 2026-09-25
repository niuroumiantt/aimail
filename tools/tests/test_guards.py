"""攻击每个守卫:每条声称的保证,至少一个用例试图违反它并断言被抓。"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import guard_attribution
import guard_hostnames
import guard_status
import guard_third_party
import guard_tokens

# ── 令牌 ─────────────────────────────────────────────────────────


def _web(tmp_path: Path, rel: str, text: str) -> Path:
    path = tmp_path / "web" / "src" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    return tmp_path / "web" / "src"


def test_hex_outside_tokens_is_caught(tmp_path):
    root = _web(tmp_path, "components/pill.tsx", 'const c = "#1f93ff";')
    assert any("字面色值" in p for p in guard_tokens.check(root))


def test_hex_inside_tokens_is_allowed(tmp_path):
    root = _web(tmp_path, "tokens/theme.css", "@theme { --color-brand: #1f93ff; }")
    assert guard_tokens.check(root) == []


def test_color_function_outside_tokens_is_caught(tmp_path):
    root = _web(tmp_path, "components/x.css", ".x { color: oklch(0.5 0.1 200); }")
    assert any("字面色值" in p for p in guard_tokens.check(root))


def test_arbitrary_value_is_caught(tmp_path):
    root = _web(tmp_path, "components/x.tsx", '<div className="p-[7px] bg-brand" />')
    assert any("任意值" in p for p in guard_tokens.check(root))


def test_arbitrary_variant_is_caught(tmp_path):
    root = _web(tmp_path, "components/x.tsx", '<div className="[&_svg]:size-4" />')
    assert any("任意值" in p for p in guard_tokens.check(root))


def test_pages_visual_class_is_caught(tmp_path):
    root = _web(tmp_path, "pages/inbox.tsx", '<div className="flex gap-2 bg-surface rounded-lg" />')
    problems = guard_tokens.check(root)
    assert any("`bg-surface`" in p for p in problems)
    assert any("`rounded-lg`" in p for p in problems)


def test_pages_layout_and_text_size_are_allowed(tmp_path):
    root = _web(
        tmp_path, "pages/inbox.tsx", '<div className="flex gap-2 p-4 text-sm hover:text-lg" />'
    )
    assert guard_tokens.check(root) == []


def test_pages_text_color_is_caught_even_with_variant_prefix(tmp_path):
    root = _web(tmp_path, "pages/inbox.tsx", '<div className="dark:text-ink-2" />')
    assert any("`text-ink-2`" in p for p in guard_tokens.check(root))


# ── 主机名 ───────────────────────────────────────────────────────


def _server(tmp_path: Path, rel: str, text: str) -> Path:
    path = tmp_path / "server" / "src" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    return tmp_path / "server" / "src"


def test_hostname_outside_backends_is_caught(tmp_path):
    root = _server(tmp_path, "aimail/api/routes.py", 'URL = "https://dgx.tail52686f.ts.net:4000"')
    assert guard_hostnames.check([root])


def test_tailnet_ip_outside_backends_is_caught(tmp_path):
    root = _server(tmp_path, "aimail/tasks/x.py", 'HOST = "100.100.1.2"')
    assert any("tailnet 地址" in p for p in guard_hostnames.check([root]))


def test_hostname_inside_backends_is_allowed(tmp_path):
    root = _server(tmp_path, "aimail/backends/spark.py", 'DEFAULT = "http://192.168.50.2:11434"')
    assert guard_hostnames.check([root]) == []


def test_other_repo_name_is_caught(tmp_path):
    root = _server(tmp_path, "aimail/store/x.py", "# 参考 niuroumiantt/infra 的做法")
    assert any("别的仓库" in p for p in guard_hostnames.check([root]))


def test_version_string_is_not_mistaken_for_an_address(tmp_path):
    root = _server(tmp_path, "aimail/api/x.py", 'VERSION = "10.1.2"')
    assert guard_hostnames.check([root]) == []


# ── STATUS ───────────────────────────────────────────────────────

STATUS_HEAD = "| 能力 | 状态 | 测试 |\n| --- | --- | --- |\n"


def _repo_with_test(tmp_path: Path, name: str) -> Path:
    tests = tmp_path / "tools" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_x.py").write_text(f"def {name}():\n    pass\n", "utf-8")
    (tmp_path / "server" / "tests").mkdir(parents=True)
    (tmp_path / "web" / "src").mkdir(parents=True)
    return tmp_path


def test_check_without_test_name_is_caught(tmp_path):
    repo = _repo_with_test(tmp_path, "test_real")
    assert any(
        "没有测试名" in p for p in guard_status.check(STATUS_HEAD + "| 收信 | ✅ | |\n", repo)
    )


def test_check_naming_missing_test_is_caught(tmp_path):
    repo = _repo_with_test(tmp_path, "test_real")
    problems = guard_status.check(STATUS_HEAD + "| 收信 | ✅ | test_imaginary |\n", repo)
    assert any("test_imaginary 不存在" in p for p in problems)


def test_check_with_existing_test_passes(tmp_path):
    repo = _repo_with_test(tmp_path, "test_real")
    assert guard_status.check(STATUS_HEAD + "| 收信 | ✅ | test_real |\n", repo) == []


def test_pending_row_needs_no_test(tmp_path):
    repo = _repo_with_test(tmp_path, "test_real")
    assert guard_status.check(STATUS_HEAD + "| 收信 | ⏳ | |\n", repo) == []


def test_frontend_test_name_is_found(tmp_path):
    repo = _repo_with_test(tmp_path, "test_real")
    (repo / "web" / "src" / "a.test.tsx").write_text('it("shell renders", () => {})', "utf-8")
    assert guard_status.check(STATUS_HEAD + "| 壳 | ✅ | shell renders |\n", repo) == []


# ── 抄来的文件 ───────────────────────────────────────────────────

REGISTRY_HEAD = "| 路径 | 来源 | 许可证 | 改了什么 |\n| --- | --- | --- | --- |\n"


def test_header_without_listing_is_caught(tmp_path):
    (tmp_path / "web" / "src").mkdir(parents=True)
    (tmp_path / "web" / "src" / "empty.svg").write_text(
        "<!-- 来源: chatwoot/chatwoot -->\n<svg/>", "utf-8"
    )
    assert any("没登记" in p for p in guard_third_party.check(REGISTRY_HEAD, tmp_path))


def test_listing_without_file_is_caught(tmp_path):
    (tmp_path / "web" / "src").mkdir(parents=True)
    registry = REGISTRY_HEAD + "| `web/src/gone.svg` | chatwoot | MIT | 无 |\n"
    assert any("不存在" in p for p in guard_third_party.check(registry, tmp_path))


def test_listed_and_headed_file_passes(tmp_path):
    (tmp_path / "web" / "src").mkdir(parents=True)
    (tmp_path / "web" / "src" / "empty.svg").write_text(
        "<!-- 来源: chatwoot/chatwoot -->\n<svg/>", "utf-8"
    )
    registry = REGISTRY_HEAD + "| `web/src/empty.svg` | chatwoot | MIT | 改了颜色 |\n"
    assert guard_third_party.check(registry, tmp_path) == []


# ── 署名 ─────────────────────────────────────────────────────────

GOOD_DERIVED = """
-- derived
CREATE TABLE message_reading (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES message(id),
  model TEXT NOT NULL,
  task_version TEXT NOT NULL,
  produced_at TEXT NOT NULL,
  body TEXT NOT NULL
);
"""


def test_derived_table_missing_attribution_is_caught():
    bad = GOOD_DERIVED.replace("  model TEXT NOT NULL,\n", "")
    assert any("model" in p for p in guard_attribution.check(bad))


def test_nullable_attribution_column_is_caught():
    bad = GOOD_DERIVED.replace("produced_at TEXT NOT NULL", "produced_at TEXT")
    assert any("produced_at" in p for p in guard_attribution.check(bad))


def test_complete_derived_table_passes():
    assert guard_attribution.check(GOOD_DERIVED) == []


def test_mention_of_marker_inside_a_comment_is_not_a_marker():
    """文件头注释里解释「-- derived 标记」这几个字,不能把下一张表当成派生表。"""
    text = (
        "-- 派生表以 `-- derived` 标记,必须带署名\n\n"
        "CREATE TABLE mailbox (\n  id INTEGER PRIMARY KEY\n);\n"
    )
    assert guard_attribution.check(text) == []


def test_unmarked_table_is_not_a_derived_table():
    plain = GOOD_DERIVED.replace("-- derived\n", "")
    assert guard_attribution.check(plain) == []


# ── 跳过即失败 ───────────────────────────────────────────────────


def test_skipped_test_fails_the_run(tmp_path):
    """conftest 里的钩子把"跳过"变成失败——这里真跑一次 pytest 验证它。"""
    repo = Path(__file__).resolve().parents[2]
    (tmp_path / "conftest.py").write_text((repo / "conftest.py").read_text("utf-8"), "utf-8")
    (tmp_path / "test_skip.py").write_text(
        textwrap.dedent(
            """
            import pytest

            @pytest.mark.skip(reason="偷懒")
            def test_lazy():
                pass

            def test_fine():
                pass
            """
        ),
        "utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode != 0, result.stdout
    assert "跳过的测试导致失败" in result.stdout


# ── 评测集 ───────────────────────────────────────────────────────


def _task(tmp_path: Path, name: str) -> tuple[Path, Path]:
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / f"{name}.py").write_text(f'TASK_VERSION = "{name}@1"\n', "utf-8")
    return tasks, tmp_path / "evals"


def test_task_without_eval_folder_is_caught(tmp_path):
    import guard_evals

    tasks, evals = _task(tmp_path, "extract_lead")
    assert any("extract_lead" in p for p in guard_evals.check(tasks, evals))


def test_task_with_run_but_no_sample_dataset_is_caught(tmp_path):
    import guard_evals

    tasks, evals = _task(tmp_path, "extract_lead")
    (evals / "extract_lead").mkdir(parents=True)
    (evals / "extract_lead" / "run.py").write_text("", "utf-8")
    assert any("dataset.sample.jsonl" in p for p in guard_evals.check(tasks, evals))


def test_task_with_complete_eval_folder_passes(tmp_path):
    import guard_evals

    tasks, evals = _task(tmp_path, "extract_lead")
    (evals / "extract_lead").mkdir(parents=True)
    (evals / "extract_lead" / "run.py").write_text("", "utf-8")
    (evals / "extract_lead" / "dataset.sample.jsonl").write_text("{}\n", "utf-8")
    assert guard_evals.check(tasks, evals) == []


def test_module_without_task_version_needs_no_evals(tmp_path):
    import guard_evals

    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "read.py").write_text("def read(): ...\n", "utf-8")
    assert guard_evals.check(tasks, tmp_path / "evals") == []
