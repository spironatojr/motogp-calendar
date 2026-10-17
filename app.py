#!/usr/bin/env python3
"""A small native GTK4 / libadwaita MotoGP calendar and Omarchy launcher."""
from __future__ import annotations

import calendar
import datetime as dt
import json
from pathlib import Path
import sys
import threading

import calendar_data as model
import race_results as results


def main():
    if '--status' in sys.argv:
        print(json.dumps(model.status()))
        return
    export_option = next((arg for arg in ('--export', '--export-iphone') if arg in sys.argv), None)
    if export_option:
        index = sys.argv.index(export_option)
        path = Path(sys.argv[index + 1])
        path.write_bytes(model.export_ics(model.load_calendar()).encode('utf-8'))
        print(path)
        return

    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    gi.require_version('GdkPixbuf', '2.0')
    gi.require_version('Graphene', '1.0')
    from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk, Pango

    if '--official' in sys.argv:
        Gio.AppInfo.launch_default_for_uri(model.CALENDAR_URL, None)
        return

    def label(text, css='', wrap=False):
        widget = Gtk.Label(label=text, xalign=0)
        widget.set_wrap(wrap)
        for name in css.split():
            widget.add_css_class(name)
        return widget

    def box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css=''):
        widget = Gtk.Box(orientation=orientation, spacing=spacing)
        for name in css.split():
            widget.add_css_class(name)
        return widget

    def button(text, callback, css=''):
        widget = Gtk.Button(label=text)
        widget.connect('clicked', lambda *_: callback())
        for name in css.split():
            widget.add_css_class(name)
        return widget

    def clear(widget):
        while widget.get_first_child():
            widget.remove(widget.get_first_child())

    class CircuitImage(Gtk.Widget):
        def __init__(self, texture, description, preview=False):
            super().__init__()
            self.texture = texture
            self.image_width = 240 if preview else 140
            self.image_height = 136 if preview else 44
            self.add_css_class('circuit-layout')
            self.set_size_request(240 if preview else 88, self.image_height)
            self.set_hexpand(not preview)
            self.set_valign(Gtk.Align.CENTER)
            self.set_opacity(1.0 if preview else 0.95)
            self.update_property([Gtk.AccessibleProperty.LABEL], [description])
            if not preview:
                self.set_has_tooltip(True)
                self.connect('query-tooltip', self.show_preview, description)

        def show_preview(self, widget, x, y, keyboard_mode, tooltip, description):
            content = box(spacing=8)
            content.append(CircuitImage(self.texture, description, preview=True))
            caption = label(description, wrap=True)
            caption.set_xalign(0.5)
            caption.set_max_width_chars(32)
            content.append(caption)
            tooltip.set_custom(content)
            return True

        def do_snapshot(self, snapshot):
            width, height = self.texture.get_width(), self.texture.get_height()
            scale = min(min(self.get_width(), self.image_width) / width,
                        min(self.get_height(), self.image_height) / height)
            bounds = Graphene.Rect().init((self.get_width() - width * scale) / 2,
                                          (self.get_height() - height * scale) / 2,
                                          width * scale, height * scale)
            snapshot.append_texture(self.texture, bounds)

    class RaceWindow(Adw.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title='MotoGP Race Calendar')
            self.set_default_size(1100, 780)
            self.set_size_request(880, 600)
            self.add_css_class('motogp')
            self.data = model.load_calendar()
            self.results = results.load_results()
            self.circuit_images = {}
            self.today = dt.date.today()
            self.only_upcoming = True
            self.query = ''
            next_race = model.next_race(self.data['races'], self.today)
            self.selected = next_race or self.data['races'][-1]
            self.month = model.race_date(self.selected).replace(day=1)
            self.overlay = Adw.ToastOverlay()
            self.set_content(self.overlay)
            outer = box(spacing=0)
            self.overlay.set_child(outer)

            header = Adw.HeaderBar()
            header.set_show_start_title_buttons(False)
            title = box(spacing=6)
            wordmark = Gtk.Picture.new_for_filename(str(Path(__file__).with_name('motogp-logo.svg')))
            wordmark.set_content_fit(Gtk.ContentFit.CONTAIN)
            wordmark.set_can_shrink(True)
            wordmark.set_size_request(164, 27)
            wordmark.set_halign(Gtk.Align.CENTER)
            wordmark.update_property([Gtk.AccessibleProperty.LABEL], ['MotoGP'])
            subtitle = label('RACE CALENDAR  /  2026', 'app-subtitle')
            subtitle.set_xalign(0.5)
            title.append(wordmark)
            title.append(subtitle)
            header.set_title_widget(title)
            header.add_css_class('app-header')
            outer.append(header)

            self.hero = box(Gtk.Orientation.HORIZONTAL, 24, 'hero')
            outer.append(self.hero)
            content = box(Gtk.Orientation.HORIZONTAL, 28, 'content')
            content.set_vexpand(True)
            outer.append(content)

            left = box(spacing=22)
            left.set_size_request(320, -1)
            left_scroll = Gtk.ScrolledWindow()
            left_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            left_scroll.set_min_content_width(340)
            left_scroll.set_hexpand(False)
            left_scroll.set_child(left)
            content.append(left_scroll)
            self.calendar_box = box(spacing=14, css='calendar-panel')
            left.append(self.calendar_box)
            self.detail = box(spacing=10, css='detail-panel')
            left.append(self.detail)
            source = button('Official MotoGP calendar  ↗', self.official, 'flat source-link')
            source.set_halign(Gtk.Align.START)
            left.append(source)
            hint = label('Weekend dates are local to the circuit.\nCheck the official timetable for session times.', 'muted fine-print', True)
            left.append(hint)

            right = box(spacing=14)
            right.set_hexpand(True)
            content.append(right)
            filters = box(Gtk.Orientation.HORIZONTAL, 12)
            right.append(filters)
            toggle_box = box(Gtk.Orientation.HORIZONTAL, 0, 'linked')
            self.upcoming_button = Gtk.ToggleButton(label='Upcoming')
            self.all_button = Gtk.ToggleButton(label='Full season')
            self.all_button.set_tooltip_text('Browse all rounds and podiums from completed Grands Prix')
            self.all_button.set_group(self.upcoming_button)
            self.upcoming_button.set_active(True)
            self.upcoming_button.connect('toggled', self.filter_changed)
            toggle_box.append(self.upcoming_button)
            toggle_box.append(self.all_button)
            filters.append(toggle_box)
            self.export_button = Gtk.Button()
            self.export_button.add_css_class('toolbar-icon-button')
            self.export_button.add_css_class('calendar-export-button')
            self.export_button.set_valign(Gtk.Align.CENTER)
            self.export_button.set_tooltip_text('Export all 22 Grand Prix weekends (.ics)')
            self.export_button.update_property(
                [Gtk.AccessibleProperty.LABEL], ['Export the entire 2026 calendar'])
            self.export_button.connect('clicked', lambda *_: self.export())
            icon_path = Path(__file__).with_name('icons') / 'calendar-arrow-down.svg'
            export_icon = Gtk.Image.new_from_file(str(icon_path))
            export_icon.set_pixel_size(18)
            self.export_button.set_child(export_icon)
            filters.append(self.export_button)
            self.refresh_button = Gtk.Button()
            self.refresh_button.add_css_class('toolbar-icon-button')
            self.refresh_button.add_css_class('calendar-refresh-button')
            self.refresh_button.set_valign(Gtk.Align.CENTER)
            self.refresh_button.set_tooltip_text('Refresh dates and Grand Prix podiums')
            self.refresh_button.update_property(
                [Gtk.AccessibleProperty.LABEL], ['Refresh calendar and race podiums'])
            self.refresh_button.connect('clicked', lambda *_: self.refresh())
            refresh_path = Path(__file__).with_name('icons') / 'refresh-cw.svg'
            refresh_icon = Gtk.Image.new_from_file(str(refresh_path))
            refresh_icon.set_pixel_size(18)
            self.refresh_spinner = Gtk.Spinner()
            self.refresh_spinner.set_size_request(18, 18)
            self.refresh_content = Gtk.Stack()
            self.refresh_content.add_named(refresh_icon, 'idle')
            self.refresh_content.add_named(self.refresh_spinner, 'busy')
            self.refresh_button.set_child(self.refresh_content)
            filters.append(self.refresh_button)
            self.count = label('', 'muted')
            self.count.set_hexpand(True)
            self.count.set_xalign(1)
            filters.append(self.count)

            search = Gtk.SearchEntry(placeholder_text='Find a Grand Prix or circuit…')
            search.connect('search-changed', self.search_changed)
            right.append(search)
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_vexpand(True)
            right.append(scroller)
            self.race_list = box(spacing=8)
            scroller.set_child(self.race_list)

            footer = box(Gtk.Orientation.HORIZONTAL, 12, 'footer')
            self.verified_label = label('', 'muted fine-print')
            footer.append(self.verified_label)
            note = label('22 rounds  ·  Five continents', 'muted fine-print')
            note.set_hexpand(True)
            note.set_xalign(1)
            footer.append(note)
            outer.append(footer)
            keys = Gtk.EventControllerKey()
            keys.connect('key-pressed', self.key_pressed)
            self.add_controller(keys)
            self.render()
            GLib.timeout_add_seconds(60, self.check_date)

        def key_pressed(self, controller, key, code, state):
            if key == Gdk.KEY_Escape:
                self.close()
                return True
            return False

        def check_date(self):
            if not self.get_visible():
                return False
            if self.today != dt.date.today():
                self.today = dt.date.today()
                self.render()
            return True

        def official(self):
            try:
                Gio.AppInfo.launch_default_for_uri(model.CALENDAR_URL, None)
            except GLib.Error as error:
                self.toast(str(error))

        def toast(self, text):
            self.overlay.add_toast(Adw.Toast.new(text))

        def render(self):
            self.render_hero()
            self.render_calendar()
            self.render_detail()
            self.render_races()
            self.verified_label.set_text(f'Dates verified {self.data["verified"]}  ·  MotoGP.com')

        def render_hero(self):
            clear(self.hero)
            race = model.next_race(self.data['races'], self.today)
            if race is None:
                text = box(spacing=7)
                text.append(label('CHEQUERED FLAG', 'eyebrow'))
                text.append(label('That’s a wrap, 2026.', 'hero-title'))
                text.append(label('Browse every Grand Prix from the season.', 'muted'))
                self.hero.append(text)
                return
            text = box(spacing=7)
            text.set_hexpand(True)
            days = (model.weekend_start(race) - self.today).days
            text.append(label(f'UP NEXT  /  ROUND {race["round"]:02d}', 'eyebrow'))
            text.append(label(f'{race["country"]} Grand Prix', 'hero-title'))
            text.append(label(f'{race["circuit"]}   ·   {model.date_range(race)} {model.YEAR}', 'hero-subtitle'))
            self.hero.append(text)
            countdown = box(spacing=0, css='countdown')
            countdown.set_valign(Gtk.Align.CENTER)
            countdown.append(label(str(days) if days > 0 else 'GO', 'count-number'))
            countdown.append(label('DAYS TO WEEKEND' if days > 0 else 'RACE WEEKEND', 'eyebrow muted'))
            self.hero.append(countdown)

        def shift_month(self, amount):
            month = self.month.month + amount
            if 1 <= month <= 12:
                self.month = dt.date(model.YEAR, month, 1)
                self.render_calendar()

        def jump_next(self):
            race = model.next_race(self.data['races'], self.today)
            if race:
                self.select(race)

        def select(self, race):
            self.selected = race
            self.month = model.race_date(race).replace(day=1)
            if model.race_date(race) < self.today and self.only_upcoming:
                self.all_button.set_active(True)
            self.render_calendar()
            self.render_detail()
            self.render_races()
            if self.selected_race_card is not None:
                GLib.idle_add(self.reveal_race, self.selected_race_card)

        def reveal_race(self, card):
            if card.get_root() is self:
                card.grab_focus()
            return False

        def render_calendar(self):
            clear(self.calendar_box)
            nav = box(Gtk.Orientation.HORIZONTAL, 5)
            title = label(f'{self.month:%B}  {model.YEAR}', 'section-title')
            title.set_hexpand(True)
            nav.append(title)
            back = button('‹', lambda: self.shift_month(-1), 'flat nav-button')
            back.set_sensitive(self.month.month > 1)
            back.set_tooltip_text('Previous month')
            nav.append(back)
            forward = button('›', lambda: self.shift_month(1), 'flat nav-button')
            forward.set_sensitive(self.month.month < 12)
            forward.set_tooltip_text('Next month')
            nav.append(forward)
            self.calendar_box.append(nav)
            grid = Gtk.Grid(column_homogeneous=True, row_homogeneous=True, column_spacing=3, row_spacing=3)
            self.calendar_box.append(grid)
            for column, day in enumerate(['M', 'T', 'W', 'T', 'F', 'S', 'S']):
                heading = Gtk.Label(label=day)
                heading.add_css_class('weekday')
                grid.attach(heading, column, 0, 1, 1)
            for row, week in enumerate(calendar.monthcalendar(model.YEAR, self.month.month), 1):
                for column, day in enumerate(week):
                    if not day:
                        grid.attach(Gtk.Label(), column, row, 1, 1)
                        continue
                    date = dt.date(model.YEAR, self.month.month, day)
                    race = next((r for r in self.data['races'] if model.weekend_start(r) <= date <= model.race_date(r)), None)
                    cell = button(str(day), (lambda r=race: self.select(r)) if race else lambda: None, 'day')
                    if race:
                        cell.add_css_class('race-day' if date == model.race_date(race) else 'weekend-day')
                        cell.set_tooltip_text(f'{race["country"]} GP · {model.date_range(race)}')
                        if race['code'] == self.selected['code']:
                            cell.add_css_class('selected-day')
                    else:
                        cell.set_focusable(False)
                    if date == self.today:
                        cell.add_css_class('today')
                    grid.attach(cell, column, row, 1, 1)
            legend = box(Gtk.Orientation.HORIZONTAL, 8)
            legend.append(label('●', 'red'))
            legend.append(label('Grand Prix', 'muted fine-print'))
            legend.append(label('○', 'red'))
            legend.append(label('Race weekend', 'muted fine-print'))
            self.calendar_box.append(legend)
            self.calendar_box.append(button('Jump to next race  →', self.jump_next, 'flat jump-button'))

        def render_detail(self):
            clear(self.detail)
            race = self.selected
            date = model.race_date(race)
            self.detail.append(label(f'ROUND {race["round"]:02d}  /  {race["flag"]}', 'eyebrow muted'))
            self.detail.append(label(f'{race["country"]} GP', 'detail-title'))
            self.detail.append(label(race['circuit'], 'muted'))
            dates = Gtk.Grid(column_spacing=8, row_spacing=10)
            self.detail.append(dates)
            for row, (title, value) in enumerate([
                    ('Weekend', model.date_range(race)),
                    ('Sprint day', f'{date - dt.timedelta(days=1):%a, %d %b}'),
                    ('Grand Prix', f'{date:%a, %d %b}')]):
                key = label(title, 'muted')
                key.set_hexpand(True)
                key.set_valign(Gtk.Align.CENTER)
                date_value = label(value, 'detail-value')
                date_value.set_xalign(1)
                date_value.set_halign(Gtk.Align.END)
                date_value.set_valign(Gtk.Align.CENTER)
                dates.attach(key, 0, row, 1, 1)
                dates.attach(date_value, 1, row, 1, 1)
            if model.race_date(race) < self.today:
                self.detail.append(button('Official race results  ↗',
                                          lambda: self.open_results(race), 'timetable-button'))
            else:
                self.detail.append(button('Session timetable  ↗', self.official, 'timetable-button'))

        def open_results(self, race):
            try:
                Gio.AppInfo.launch_default_for_uri(results.results_url(race), None)
            except GLib.Error as error:
                self.toast(str(error))

        def podium_widget(self, result):
            panel = box(spacing=10, css='podium-panel')
            panel.set_tooltip_text(f'Grand Prix race · MotoGP.com · Verified {result["verified"]}')
            panel.append(label('GRAND PRIX PODIUM', 'podium-caption'))
            places = box(Gtk.Orientation.HORIZONTAL, 14)
            places.set_halign(Gtk.Align.CENTER)
            panel.append(places)
            for rider, medal in zip(result['podium'], ('gold', 'silver', 'bronze')):
                place = box(Gtk.Orientation.HORIZONTAL, 8)
                place.set_halign(Gtk.Align.CENTER)
                place.set_valign(Gtk.Align.START)
                rank = label(str(rider['position']), f'podium-rank {medal}')
                rank.set_xalign(0.5)
                rank.set_valign(Gtk.Align.START)
                place.append(rank)
                identity = box(spacing=3)
                name = label(rider['rider'], 'podium-rider', True)
                name.set_xalign(0.5)
                name.set_justify(Gtk.Justification.CENTER)
                name.set_max_width_chars(19)
                name.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                team = label(rider['team'], 'podium-team', True)
                team.set_xalign(0.5)
                team.set_justify(Gtk.Justification.CENTER)
                team.set_max_width_chars(22)
                team.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                identity.append(name)
                identity.append(team)
                place.append(identity)
                places.append(place)
            return panel

        def filter_changed(self, widget):
            self.only_upcoming = widget.get_active()
            self.render_races()

        def search_changed(self, widget):
            self.query = widget.get_text().casefold().strip()
            self.render_races()

        def circuit_widget(self, race):
            code = race['code']
            if code not in self.circuit_images:
                path = Path(__file__).with_name('circuits') / f'{code}.png'
                try:
                    image = GdkPixbuf.Pixbuf.new_from_file(str(path))
                    # Official images include transparent margins. Crop their display
                    # bounds so every track fits the same small header area.
                    if image.get_has_alpha():
                        width, height = image.get_width(), image.get_height()
                        pixels = image.get_pixels()
                        stride, channels = image.get_rowstride(), image.get_n_channels()
                        left, top, right, bottom = width, height, 0, 0
                        for y in range(height):
                            start = y * stride
                            alpha = pixels[start + channels - 1:start + width * channels:channels]
                            if alpha.strip(b'\0'):
                                left = min(left, width - len(alpha.lstrip(b'\0')))
                                right = max(right, len(alpha.rstrip(b'\0')))
                                top, bottom = min(top, y), y + 1
                        if right > left and bottom > top:
                            image = image.new_subpixbuf(left, top, right - left, bottom - top)
                    self.circuit_images[code] = Gdk.Texture.new_for_pixbuf(image)
                except GLib.Error:
                    return None
            description = f'{race["circuit"]} circuit layout'
            return CircuitImage(self.circuit_images[code], description)

        def render_races(self):
            clear(self.race_list)
            self.selected_race_card = None
            races = [r for r in self.data['races']
                     if (not self.only_upcoming or model.race_date(r) >= self.today)
                     and self.query in f'{r["country"]} {r["circuit"]}'.casefold()]
            self.count.set_text(f'{len(races)} rounds')
            next_race = model.next_race(self.data['races'], self.today)
            last_month = None
            for race in races:
                date = model.race_date(race)
                if date.month != last_month:
                    self.race_list.append(label(f'{date:%B}'.upper(), 'month-heading'))
                    last_month = date.month
                card = Gtk.Button()
                card.add_css_class('race-card')
                if race['code'] == self.selected['code']:
                    card.add_css_class('selected-card')
                    self.selected_race_card = card
                card.connect('clicked', lambda _, r=race: self.select(r))
                row = box(Gtk.Orientation.HORIZONTAL, 16)
                date_box = box(spacing=0, css='race-date')
                date_box.set_size_request(48, -1)
                date_box.append(label(f'{date.day:02d}', 'date-number'))
                date_box.append(label(f'{date:%b}'.upper(), 'date-month'))
                row.append(date_box)
                info = box(spacing=4)
                flag = ''.join(chr(0x1F1E6 + ord(char) - ord('A')) for char in race['flag'])
                title_text = f'{flag}  {race["country"]} Grand Prix'
                title = label(title_text, 'race-title')
                title.set_ellipsize(Pango.EllipsizeMode.END)
                title.set_tooltip_text(title_text)
                subtitle = label(f'{race["circuit"]}  ·  {model.date_range(race)}', 'muted fine-print')
                subtitle.set_ellipsize(Pango.EllipsizeMode.END)
                info.append(title)
                info.append(subtitle)
                row.append(info)
                circuit = self.circuit_widget(race)
                if circuit is not None:
                    row.append(circuit)
                else:
                    info.set_hexpand(True)
                badge_box = box(spacing=4)
                badge_box.set_valign(Gtk.Align.CENTER)
                badge = label(f'R{race["round"]:02d}', 'round-badge')
                badge.set_xalign(1)
                badge_box.append(badge)
                result = results.result_for(self.results, race, self.today)
                if result is not None:
                    badge_box.append(label('FINISHED', 'muted fine-print'))
                elif next_race and race['code'] == next_race['code']:
                    badge_box.append(label('NEXT', 'next-badge'))
                elif date < self.today:
                    badge_box.append(label('PAST', 'muted fine-print'))
                row.append(badge_box)
                contents = box(spacing=0)
                contents.append(row)
                if result is not None:
                    contents.append(self.podium_widget(result))
                elif date < self.today:
                    contents.append(label('Podium not available yet. Refresh to check results.',
                                          'podium-pending', True))
                card.set_child(contents)
                self.race_list.append(card)
            if not races:
                self.race_list.append(label('No races found.' if self.query else 'The 2026 season is complete.\nSwitch to Full season to browse every round.', 'empty-state muted', True))

        def refresh(self):
            self.refresh_button.set_sensitive(False)
            self.refresh_button.set_tooltip_text('Checking MotoGP dates and podiums…')
            self.refresh_content.set_visible_child_name('busy')
            self.refresh_spinner.start()
            saved_races = self.data['races']

            def work():
                try:
                    data, error = model.refresh_calendar(), None
                except Exception as exc:
                    data, error = None, str(exc)
                try:
                    podiums, podium_errors = results.refresh_results(data['races'] if data else saved_races)
                except Exception as exc:
                    podiums, podium_errors = None, [str(exc)]
                GLib.idle_add(self.refreshed, data, error, podiums, podium_errors)

            threading.Thread(target=work, daemon=True).start()

        def refreshed(self, data, error, podiums, podium_errors):
            self.refresh_button.set_sensitive(True)
            self.refresh_spinner.stop()
            self.refresh_content.set_visible_child_name('idle')
            self.refresh_button.set_tooltip_text('Refresh dates and Grand Prix podiums')
            if error:
                print(f'Calendar refresh: {error}', file=sys.stderr)
            if data is not None:
                code = self.selected['code']
                self.data = data
                self.selected = next(r for r in data['races'] if r['code'] == code)
                self.month = model.race_date(self.selected).replace(day=1)
            if podiums is not None:
                self.results = podiums
            self.render()
            if error or podium_errors:
                self.toast('Some updates could not be checked. Saved dates and podiums remain available.')
                for message in podium_errors:
                    print(f'Podium refresh: {message}', file=sys.stderr)
            else:
                self.toast('Calendar and Grand Prix podiums are up to date.')
            return False

        def export(self):
            dialog = Gtk.FileDialog(
                title='Export MotoGP race weekends',
                initial_name='MotoGP-2026.ics')
            file_filter = Gtk.FileFilter()
            file_filter.set_name('iCalendar (.ics)')
            file_filter.add_pattern('*.ics')
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(file_filter)
            dialog.set_filters(filters)
            dialog.set_default_filter(file_filter)
            dialog.save(self, None, self.exported)

        def exported(self, dialog, result):
            try:
                file = dialog.save_finish(result)
                file.replace_contents(model.export_ics(self.data).encode('utf-8'), None, False, Gio.FileCreateFlags.NONE, None)
                self.toast('Exported 22 race weekends. Import the .ics file into your calendar.')
            except GLib.Error as error:
                if not error.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED):
                    self.toast(f'Could not export: {error.message}')

    class RaceApp(Adw.Application):
        def __init__(self):
            super().__init__(application_id='local.motogp.Calendar')

        def do_activate(self):
            window = self.get_active_window()
            if window is None:
                provider = Gtk.CssProvider()
                provider.load_from_path(str(Path(__file__).with_name('style.css')))
                Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                self.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
                window = RaceWindow(self)
            window.present()
            if '--smoke-test' in sys.argv:
                GLib.timeout_add(1800, lambda: (self.quit(), False)[1])

    app = RaceApp()
    app.run([sys.argv[0]])


if __name__ == '__main__':
    main()
