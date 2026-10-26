#!/usr/bin/env python3
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, DataTable, Button, Input, Static, RichLog
from textual.binding import Binding

from core.linker import ModManager
from core.config import auto_find_cyberpunk


class CyberpunkModLauncher(App):
    TITLE = "CYBERPUNK 2077 // LINUX MOD SYSTEM"
    SUB_TITLE = "Symlink Deployment Protocol"

    CSS = """
    Screen {
        background: #0d0d12;
        color: #00f0ff;
    }
    Header {
        background: #fcee0a;
        color: #000000;
        text-style: bold;
    }
    Footer {
        background: #1a1a24;
        color: #fcee0a;
    }
    #top-bar {
        height: 5;
        background: #14141d;
        border: heavy #fcee0a;
        padding: 0 1;
        margin: 1 1 0 1;
        align: left middle;
    }
    #path-label {
        width: auto;
        color: #fcee0a;
        text-style: bold;
        margin-right: 1;
    }
    #path-input {
        width: 1fr;
        background: #0d0d12;
        border: tall #00f0ff;
        color: #ffffff;
    }
    #btn-find {
        margin-left: 1;
        background: #00f0ff;
        color: #000000;
        text-style: bold;
    }
    #main-area {
        height: 1fr;
        margin: 1;
    }
    #mods-table {
        width: 2fr;
        height: 100%;
        border: heavy #00f0ff;
        background: #111118;
    }
    DataTable > .datatable--header {
        background: #00f0ff;
        color: #000000;
        text-style: bold;
    }
    DataTable > .datatable--cursor {
        background: #ff003c;
        color: #ffffff;
        text-style: bold;
    }
    #side-panel {
        width: 1fr;
        height: 100%;
        margin-left: 1;
        border: heavy #ff003c;
        background: #14141d;
        padding: 1;
    }
    .panel-title {
        color: #fcee0a;
        text-style: bold;
        margin-bottom: 1;
    }
    Button {
        width: 100%;
        margin-bottom: 1;
        text-style: bold;
    }
    #btn-toggle { background: #fcee0a; color: #000000; }
    #btn-install { background: #00f0ff; color: #000000; }
    #btn-remove { background: #ff003c; color: #ffffff; }
    #archive-input {
        margin-bottom: 1;
        border: tall #fcee0a;
        background: #0d0d12;
        color: #ffffff;
    }
    #log-box {
        height: 8;
        margin: 0 1 1 1;
        border: solid #333344;
        background: #08080c;
        color: #a0a0b0;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_mod", "Увімк/Вимк мод"),
        Binding("d", "delete_mod", "Видалити мод"),
        Binding("f", "auto_detect", "Автопошук гри"),
        Binding("q", "quit", "Вихід"),
    ]

    def __init__(self):
        super().__init__()
        self.mgr = ModManager()

    def compose(self) -> ComposeResult:
        yield Header()

        # Верхня панель зі шляхом до гри
        with Horizontal(id="top-bar"):
            yield Static("ШЛЯХ ДО ГРИ:", id="path-label")
            yield Input(value=str(self.mgr.state_mgr.game_path), id="path-input")
            yield Button("АВТОПОШУК [F]", id="btn-find")

        # Центральна частина: таблиця модів та панель керування
        with Horizontal(id="main-area"):
            yield DataTable(id="mods-table", cursor_type="row")

            with Vertical(id="side-panel"):
                yield Static("// КЕРУВАННЯ МОДОМ", classes="panel-title")
                yield Button("УВІМК / ВИМК [SPACE]", id="btn-toggle")
                yield Button("ВИДАЛИТИ МОД [D]", id="btn-remove")

                yield Static("\n// ДОДАТИ З АРХІВУ (.zip/.7z/.rar)", classes="panel-title")
                yield Input(
                    placeholder="Шлях до архіву (напр. ~/Downloads/mod.zip)",
                    id="archive-input"
                )
                yield Button("ВСТАНОВИТИ АРХІВ", id="btn-install")

        # Нижній лог подій
        yield RichLog(id="log-box", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#mods-table", DataTable)
        table.add_columns("СТАТУС", "НАЗВА МОДА", "ФАЙЛІВ (SYMLINKS)")
        self.refresh_table()
        self.check_game_path()

    def log_msg(self, text: str) -> None:
        log = self.query_one("#log-box", RichLog)
        log.write(text)

    def check_game_path(self) -> None:
        gp = self.mgr.state_mgr.game_path
        exe = gp / "bin/x64/Cyberpunk2077.exe"
        if exe.exists():
            self.log_msg(f"[bold green][OK][/] Знайдено Cyberpunk 2077: {gp}")
        else:
            self.log_msg(f"[bold red][!][/] Cyberpunk2077.exe не знайдено у: {gp}")

    def refresh_table(self) -> None:
        table = self.query_one("#mods-table", DataTable)
        table.clear()
        mods = self.mgr.state_mgr.state.get("mods", {})
        for name, data in mods.items():
            status = "[bold green]● ACTIVE[/]" if data["enabled"] else "[bold red]○ OFF[/]"
            table.add_row(status, name, str(len(data["links"])), key=name)

    def get_selected_mod(self) -> str | None:
        table = self.query_one("#mods-table", DataTable)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        return row_key.value

    # --- Дії ---
    def action_auto_detect(self) -> None:
        found = auto_find_cyberpunk()
        self.mgr.state_mgr.game_path = str(found)
        self.query_one("#path-input", Input).value = str(found)
        self.check_game_path()

    def action_toggle_mod(self) -> None:
        mod_name = self.get_selected_mod()
        if not mod_name:
            self.log_msg("[yellow]Спочатку виберіть мод у списку.[/]")
            return
        try:
            is_enabled = self.mgr.state_mgr.state["mods"][mod_name]["enabled"]
            if is_enabled:
                self.mgr.disable_mod(mod_name)
                self.log_msg(f"[yellow][-] Мод '{mod_name}' вимкнено.[/]")
            else:
                self.mgr.enable_mod(mod_name)
                self.log_msg(f"[green][+] Мод '{mod_name}' активовано![/]")
            self.refresh_table()
        except Exception as e:
            self.log_msg(f"[bold red][ПОМИЛКА][/] {e}")

    def action_delete_mod(self) -> None:
        mod_name = self.get_selected_mod()
        if not mod_name:
            return
        try:
            self.mgr.remove_mod(mod_name)
            self.log_msg(f"[red][x] Мод '{mod_name}' повністю видалено.[/]")
            self.refresh_table()
        except Exception as e:
            self.log_msg(f"[bold red][ПОМИЛКА][/] {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-find":
            self.action_auto_detect()
        elif btn_id == "btn-toggle":
            self.action_toggle_mod()
        elif btn_id == "btn-remove":
            self.action_delete_mod()
        elif btn_id == "btn-install":
            arch_input = self.query_one("#archive-input", Input)
            raw_path = arch_input.value.strip().strip("'\"")
            if not raw_path:
                self.log_msg("[yellow]Введіть шлях до архіву (або перетягніть файл у поле).[/]")
                return
            try:
                expanded_path = str(Path(raw_path).expanduser())
                self.log_msg(f"[cyan][*] Встановлення {expanded_path}...[/]")
                self.mgr.install_from_archive(expanded_path)
                arch_input.value = ""
                self.refresh_table()
                self.log_msg("[bold green][+] Мод успішно встановлено та злінковано![/]")
            except Exception as e:
                self.log_msg(f"[bold red][ПОМИЛКА ВСТАНОВЛЕННЯ][/] {e}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "path-input":
            self.mgr.state_mgr.game_path = event.value
            self.check_game_path()


if __name__ == "__main__":
    app = CyberpunkModLauncher()
    app.run()