import sys
from pathlib import Path
import tkinter as tk
from web_panel import WebPanel

def run(tmp_path):
    import launcher
    WebPanel.startup = lambda self: None
    env={'STATE_FILE':str(tmp_path/'meta/state.json'),'DOCUMENTS_ROOT':str(tmp_path/'docs'),'WEB_DOWNLOADS_PATH':str(tmp_path/'docs'),'UNIFIED_DOCUMENTS':'true','RENAME_FROM_TITLE':'false'}
    launcher.environment = lambda: env
    def inspect(window):
        window.geometry('1040x640'); window.update()
        assert window.title().endswith('1.0.5')
        panel=next(child for child in window.winfo_children() if isinstance(child,WebPanel))
        try:
            assert panel.view is None
            assert panel.startup_job is None
            assert not panel.content.winfo_ismapped()
            assert panel.welcome.winfo_ismapped()
            assert all(button.cget('style') != 'Primary.TButton' for button in panel.nav_buttons.values())
            for view in ['site','local']:
                panel.switch_view(view);window.update()
                controls=[panel.filter_box,panel.category_box,panel.year_box,panel.search_entry,*panel.nav_buttons.values(),panel.login_settings_button,panel.cancel_button,*panel.command_bar.winfo_children()[:3]]
                controls+=list(panel.site_tools.winfo_children())+list(panel.site_actions.winfo_children()) if view=='site' else list(panel.local_tools.winfo_children())
                for control in controls:
                    assert control.winfo_ismapped()
                    assert control.winfo_rooty()+control.winfo_height() <= window.winfo_rooty()+window.winfo_height()
                    assert control.winfo_rootx()+control.winfo_width() <= window.winfo_rootx()+window.winfo_width()
        finally:
            panel.destroy();window.destroy()
    tk.Tk.mainloop = inspect
    launcher.main()

run(Path(sys.argv[1]))
