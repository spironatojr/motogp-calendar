# MotoGP Calendar for Omarchy

A native GTK4/libadwaita calendar with a Quickshell bar launcher. Uses the Python,
GTK4, libadwaita and Quickshell packages already installed on this desktop.

The header uses the official white MotoGP SVG from the
[MotoGP homepage](https://www.motogp.com/), saved as `motogp-logo.svg` from
`https://static.dorna.com/assets/logos/mgp/brand/mgp-logo-on-dark.svg?v2`.
The app icon is the site's `mgp-favicon-on-dark-180x180.png`, saved as `icon.png`.
Both assets were downloaded on October 17, 2026 and are bundled for offline use.

Click **MotoGP · AUS 25 Oct** in the left side of the Omarchy bar to open the app.
Right-click the launcher to open the official MotoGP calendar. The application
also appears as **MotoGP Race Calendar** in the app launcher and **MotoGP Calendar**
in the Omarchy menu. Escape closes the calendar.

The calendar includes month navigation, highlighted race weekends, an upcoming/full
season view, circuit search, weekend details and a calendar export icon beside
**Full season**, above the race list. Export
creates 22 all-day weekend events with stable IDs, circuit locations and exclusive
end dates. Dates use the circuit's local calendar; exact session times are available
through **Session timetable** on the official site.
The refresh icon sits beside the export icon with the same size and appearance.
It checks dates and podiums, shows a spinner while checking, and returns to the
Lucide refresh icon afterward. Both actions use tooltips and accessible names.

**Full season** shows the Grand Prix podium inside each completed race card:
first, second and third place, with each rider's team as listed in that race's
official classification. Gold, silver and bronze position badges accompany the
names. Sprint results are excluded. Selecting a past weekend in the month calendar
automatically switches to the full season and brings its card into view.
**Official race results** opens the selected race's classification on MotoGP.com.
Each card also centers its official circuit outline between the Grand Prix name
and round number. Outlines fit within the existing header height, including cards
with podiums. The 22 original PNG assets are bundled in `circuits/`; `sources.json`
records their official URLs. They work offline.
Outlines use up to 140 × 44 pixels within the existing header; hovering a circuit
shows a larger 240 × 136 pixel preview with its name.

The app bundles verified podiums for the first 17 Grands Prix of 2026, through
Indonesia, in `podiums-2026.json`. They work offline. **Refresh** checks both the
calendar and the official results API and caches newly completed podiums. Unavailable
results keep the saved podiums; an unconfirmed result never appears as a podium.

Click the calendar icon to the right of **Full season** to save
`MotoGP-2026.ics`. This exports all 22 race weekends, regardless of the selected GP
or the active list filter. The icon is Lucide's `calendar-arrow-down`, bundled in
`icons/` with its license. It uses the standard iCalendar
format, including all-day dates, UTF-8 text and stable event IDs. To import on an
iPhone, email the file to yourself and open its attachment in Apple Mail, then use
the calendar import option ([Apple's instructions](https://support.apple.com/en-ie/guide/iphone/ipha0d932e96/26/ios/26)).
This creates a one-time copy of the 22 race weekends; it is not a subscription.

Dates were checked against the [official 2026 calendar](https://www.motogp.com/en/news/2026/01/01/2026-motogp-calendar/755478)
on October 17, 2026, including Qatar on November 8, Portugal on November 22 and
Valencia on November 29. The initial calendar works offline. **Refresh** checks
that official article in a background thread and saves a validated local cache.
An unavailable or changed source keeps the existing calendar. This release covers
the 2026 season; it does not automatically add later seasons or subscribe your
calendar app to future updates. Sprint dates follow the Saturday weekend format;
check the official timetable for session changes.

## Install or update

```sh
python install.py
```

The installer copies the app to `~/.local/share/motogp-calendar`, the launcher to
`~/.local/bin/motogp-calendar`, and the widget to
`~/.config/omarchy/plugins/local.motogp`. It enables the widget after the workspaces
on the left of the bar and adds an Omarchy menu entry. The shell hot-reloads these
changes. Existing configuration and app files are backed up in `backups/` here.
A small `~/.config/hypr/motogp.lua` rule opens the calendar centered at a readable
size; `hyprland.lua` loads it. It never edits `/usr/share/omarchy`.

## Commands

```sh
motogp-calendar                         # open or focus the app
motogp-calendar --status                # JSON next-race label; no GUI imports
motogp-calendar --official              # open the official schedule
motogp-calendar --export MotoGP-2026.ics # export all weekend events
python -m unittest discover -s tests -v
omarchy plugin validate ./plugin
```

The cached dates live in `${XDG_CACHE_HOME:-~/.cache}/motogp-calendar/2026.json`;
cached podiums use `podiums-2026.json` in the same directory.
The bar reads the offline cache once a minute and starts no persistent background
service. The application runs as a single instance through the desktop session bus.

To remove the integration, run `omarchy plugin disable local.motogp`, delete the
`motogp-calendar` entry from the Omarchy menu extensions, then remove the app,
launcher, desktop entry (`~/.local/share/applications/local.motogp.Calendar.desktop`)
and plugin directories listed above.
Also remove `require("hypr.motogp")` from `~/.config/hypr/hyprland.lua` and delete
`~/.config/hypr/motogp.lua`, then run `hyprctl reload`.
