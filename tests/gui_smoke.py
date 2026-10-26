#!/usr/bin/env python3
"""Run a real Qt window in offscreen mode with isolated demo mods.

This is a visual/interaction smoke check, not a filesystem deployment test.
No real Steam or user mod directory is touched.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    with tempfile.TemporaryDirectory(prefix="cp2077-gui-smoke-") as home:
        os.environ["HOME"] = home

        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        import core.config as config
        import gui

        game = Path(home) / "Demo Cyberpunk 2077"
        (game / "bin/x64").mkdir(parents=True)
        (game / "bin/x64/Cyberpunk2077.exe").write_bytes(b"MZ")

        sample_mods = [
            ("Cyberware-EX 9429 1.6.0 2026-10-25T08-53Z aI50IAAsU",
             "r6/scripts/CyberwareEx/CyberwareEx.reds", True, False),
            ("ArchiveXL 4198 1.28.0 2026-10-25T08-10Z Xx",
             "archive/pc/mod/archive_demo.archive", True, False),
            ("Visual Preset 30000 2.1.0 2026-10-25T12-00Z Demo",
             "archive/pc/mod/visual_demo.archive", False, False),
            ("Needs Repair 55555 1.0.0 2026-10-25T12-00Z Demo",
             "r6/scripts/repair_demo.reds", True, True),
        ]
        state = {"game_path": str(game), "mods": {}}
        for name, rel, enabled, damaged in sample_mods:
            source = config.MODS_DIR / name / rel
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("demo content", encoding="utf-8")
            state["mods"][name] = {
                "enabled": enabled,
                "links": [rel] if enabled else [],
            }
            if enabled and not damaged:
                target = game / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(source)
        config.APP_DIR.mkdir(parents=True, exist_ok=True)
        config.STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )

        app = QApplication([])
        with __import__("unittest.mock", fromlist=["patch"]).patch.object(
            gui, "get_game_version", return_value="2.5"
        ):
            window = gui.CyberpunkModGUI()
        window.resize(1500, 900)
        window.show()
        app.processEvents()

        assert window.table.rowCount() == 4, "Four demo mods should be visible"
        assert window.status_filter.count() == 4
        assert window.mod_health[sample_mods[3][0]]["level"] == "repairable"
        assert window.lbl_list_count.text().startswith("4")
        assert window.status_filter.itemText(0) == "All mods"
        assert window.status_filter.itemText(3) == "Needs attention"
        assert window.search_input.placeholderText() == "Search mods by name or version..."
        assert window.table.horizontalHeaderItem(1).text() == "HEALTH"
        # User-defined mod names are preserved; all app-owned labels are English.
        gui_source = (Path(__file__).resolve().parents[1] / "gui.py").read_text(encoding="utf-8")
        assert not any(0x0400 <= ord(char) <= 0x04FF for char in gui_source), (
            "UI source contains untranslated Cyrillic strings"
        )
        active_pills = [
            pill for pill in window.details_panel.status_pill_holder.findChildren(gui.StatusPill)
            if pill.isVisible()
        ]
        assert len(active_pills) == 1, "Exactly one inspector status pill must be visible"
        window.verify_all_symlinks()
        assert "REPAIR" in window.log_box.toPlainText() or "ISSUE" in window.log_box.toPlainText()

        if screenshot := os.environ.get("GUI_PREVIEW_PATH"):
            output = Path(screenshot)
            output.parent.mkdir(parents=True, exist_ok=True)
            assert window.grab().save(str(output), "PNG")

        window.status_filter.setCurrentIndex(3)
        app.processEvents()
        assert window.table.rowCount() == 1, "Issues filter must show only damaged mod"
        window.status_filter.setCurrentIndex(0)
        app.processEvents()
        assert window.table.rowCount() == 4, "Reset filter must restore all mods"

        window.search_input.setText("Cyberware")
        app.processEvents()
        assert window.table.rowCount() == 1
        window.search_input.clear()
        window.table.selectRow(0)
        app.processEvents()
        assert window.details_panel.lbl_name.text() != "NO MOD SELECTED"
        assert window.details_panel.lbl_mod_meta.text().startswith("NEXUS #")
        window.details_panel.scroller.verticalScrollBar().setValue(100)
        window.table.selectRow(1)
        app.processEvents()
        assert window.details_panel.scroller.verticalScrollBar().value() == 0
        steam_dialog = gui.SteamConfigDialog(game)
        assert any("STEAM LAUNCH OPTIONS" in label.text()
                   for label in steam_dialog.findChildren(gui.QLabel))
        assert steam_dialog.btn_copy.text() == "COPY LAUNCH OPTIONS"
        steam_dialog.close()
        window._copy_log()
        assert QApplication.clipboard().text()
        window._clear_log()
        assert window.lbl_log_count.text() == "0 ENTRIES"
        window.close()
        app.quit()
        print("Qt GUI smoke test passed (offscreen, isolated demo filesystem)")


if __name__ == "__main__":
    main()
