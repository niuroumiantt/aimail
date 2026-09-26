import os
import subprocess
from pathlib import Path


def test_install_rollback_preserves_legacy_service_activation_state(tmp_path):
    installer = Path(__file__).parents[2] / "deploy/install_mini.sh"
    source = installer.read_text()
    body = source.split("restore_legacy_service() {", 1)[1].split("\n}", 1)[0]
    function = "restore_legacy_service() {" + body + "\n}"

    for was_active in (False, True):
        case_dir = tmp_path / str(was_active)
        case_dir.mkdir()
        backup = case_dir / "backup.plist"
        legacy_plist = case_dir / "legacy.plist"
        new_plist = case_dir / "new.plist"
        launch_log = case_dir / "launchctl.log"
        backup.write_text("preserved legacy service\n")
        script = (
            'launchctl() { printf "%s\\n" "$*" >> "$LAUNCH_LOG"; }\n'
            + function
            + "\nfalse\nrestore_legacy_service\nexit 0\n"
        )
        env = os.environ | {
            "LEGACY_STOPPED": "1",
            "LEGACY_WAS_ACTIVE": str(int(was_active)),
            "LEGACY_BACKUP": str(backup),
            "LEGACY_PLIST": str(legacy_plist),
            "PLIST": str(new_plist),
            "LAUNCH_LOG": str(launch_log),
        }
        subprocess.run(["bash", "-c", script], env=env, check=True, capture_output=True)

        assert legacy_plist.read_text() == "preserved legacy service\n"
        calls = launch_log.read_text()
        assert ("bootstrap" in calls) is was_active
