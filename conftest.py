"""跳过的测试导致整次运行失败。

跳过等于把一条保证悄悄撤回,而 STATUS 里的 ✅ 还挂在那里。
要么修好,要么删掉并把 STATUS 改成 ⏳——没有第三种。
"""

from __future__ import annotations


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001 —— pytest 钩子签名固定
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    skipped = reporter.stats.get("skipped", []) if reporter else []
    if skipped:
        reporter.write_line(
            f"有 {len(skipped)} 个测试被跳过 —— 跳过的测试导致失败(见 conftest.py)", red=True
        )
        session.exitstatus = 1
