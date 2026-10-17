#!/usr/bin/env python3
"""Install the calendar into user directories and enable its Omarchy widget."""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess

from app_version import VERSION

SOURCE = Path(__file__).resolve().parent
HOME = Path.home()
DATA = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share'))
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config'))
APP = DATA / 'motogp-calendar'
PLUGIN = CONFIG / 'omarchy/plugins/local.motogp'
BACKUP = SOURCE / 'backups' / dt.datetime.now().strftime('%Y%m%d-%H%M%S')


def backup(path):
    if path.exists():
        BACKUP.mkdir(parents=True, exist_ok=True)
        target = BACKUP / str(path.relative_to(HOME)).replace('/', '__')
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)


def write(path, content, executable=False):
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if executable:
        path.chmod(0o755)


def strip_comments(text):
    """Strip JSONC comments while preserving quoted strings."""
    result, i, quoted = [], 0, False
    while i < len(text):
        c = text[i]
        if quoted:
            result.append(c)
            if c == '\\' and i + 1 < len(text):
                i += 1
                result.append(text[i])
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
            result.append(c)
        elif text[i:i+2] == '//':
            end = text.find('\n', i)
            i = len(text) if end < 0 else end
            continue
        elif text[i:i+2] == '/*':
            end = text.find('*/', i+2)
            if end < 0:
                raise ValueError('Unterminated JSONC comment')
            i = end+2
            continue
        else:
            result.append(c)
        i += 1
    return ''.join(result)


def main():
    manifest = json.loads((SOURCE / 'plugin/manifest.json').read_text())
    if manifest['version'] != VERSION:
        raise ValueError('Plugin version does not match VERSION. Run scripts/release.py check.')
    subprocess.run(['omarchy', 'plugin', 'validate', str(SOURCE / 'plugin')], check=True)
    backup(APP)
    APP.mkdir(parents=True, exist_ok=True)
    for name in ('VERSION', 'app_version.py', 'app.py', 'calendar_data.py', 'race_results.py', 'podiums-2026.json',
                 'style.css', 'motogp-logo.svg', 'icon.png'):
        shutil.copy2(SOURCE / name, APP / name)
    shutil.copytree(SOURCE / 'circuits', APP / 'circuits', dirs_exist_ok=True)
    shutil.copytree(SOURCE / 'icons', APP / 'icons', dirs_exist_ok=True)
    backup(PLUGIN)
    shutil.copytree(SOURCE / 'plugin', PLUGIN, dirs_exist_ok=True)
    (PLUGIN / 'bin/motogp-calendar').chmod(0o755)
    launcher = HOME / '.local/bin/motogp-calendar'
    write(launcher, (SOURCE / 'plugin/bin/motogp-calendar').read_text(), executable=True)
    write(DATA / 'applications/local.motogp.Calendar.desktop',
          '[Desktop Entry]\nType=Application\nName=MotoGP Race Calendar\n'
          'Comment=Grand Prix weekends, upcoming races, and calendar export\n'
          f'Exec="{launcher}"\nIcon={APP / "icon.png"}\n'
          'Terminal=false\nCategories=Office;Calendar;\nKeywords=MotoGP;race;calendar;motorcycle;\n'
          'StartupNotify=true\nStartupWMClass=local.motogp.Calendar\n')

    shell = CONFIG / 'omarchy/shell.json'
    backup(shell)
    subprocess.run(['omarchy-shell', 'shell', 'rescanPlugins'], check=True)
    subprocess.run(['omarchy', 'plugin', 'enable', 'local.motogp', '--section', 'left',
                    '--after', 'omarchy.workspaces'], check=True)

    write(CONFIG / 'hypr/motogp.lua', (SOURCE / 'motogp.lua').read_text())
    hypr_config = CONFIG / 'hypr/hyprland.lua'
    hypr_text = hypr_config.read_text()
    if 'require("hypr.motogp")' not in hypr_text:
        write(hypr_config, hypr_text.rstrip() + '\n\n-- MotoGP race calendar window.\nrequire("hypr.motogp")\n')
    subprocess.run(['hyprctl', 'reload'], check=True)
    errors = subprocess.check_output(['hyprctl', 'configerrors'], text=True).strip()
    if errors and errors != 'ok':
        raise RuntimeError('Hyprland configuration errors: ' + errors)

    menu = CONFIG / 'omarchy/extensions/omarchy-menu.jsonc'
    original = menu.read_text() if menu.exists() else '{}\n'
    cleaned = strip_comments(original)
    # Preserve the user's comments and every existing entry verbatim.
    if '"motogp-calendar"' not in cleaned:
        end = original.rfind('}')
        if end < 0:
            raise ValueError('Omarchy menu must contain a JSONC object')
        prefix = strip_comments(original[:end]).rstrip()
        comma = '' if prefix.endswith(('{', ',')) else ','
        entry = {'icon': '', 'label': 'MotoGP Calendar',
                 'action': f'"{launcher}"', 'description': 'Race weekends and the full 2026 season'}
        addition = comma + '\n  "motogp-calendar": ' + json.dumps(entry, ensure_ascii=False) + '\n'
        write(menu, original[:end] + addition + original[end:])

    subprocess.run(['update-desktop-database', str(DATA / 'applications')], check=False)
    print(f'Installed MotoGP Calendar {VERSION}: {APP}')
    print(f'Installed bar widget: {PLUGIN}')
    print(f'Backups: {BACKUP}')


if __name__ == '__main__':
    main()
