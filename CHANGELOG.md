# Changelog

App releases follow [Semantic Versioning](https://semver.org/). The season year
and the date of the last calendar/results refresh are separate from the app version.

## [Unreleased]

### Changed

- Show only the checkered flag icon in the Omarchy bar, keeping next-race details
  in the tooltip.
- Place the MotoGP widget on the right of the bar, after the system tray.

## [1.0.0] - 2026-10-17

### Added

- Native GTK4/libadwaita calendar for all 22 MotoGP weekends of the 2026 season.
- Upcoming and full-season views, circuit search, month navigation and race details.
- Bundled circuit outlines and Grand Prix podiums for offline browsing.
- Calendar and podium refresh, plus iCalendar export for all race weekends.
- Omarchy bar launcher, application menu entry and installer with local backups.
- App screenshots in the README.
- `--version`, automated tests, version checks and release packaging with SHA-256 checksums.

### Compatibility

- Requires Omarchy with its Python, GTK4, libadwaita and Quickshell packages.
- Covers the 2026 season; exported calendars are one-time imports.
- Local refresh caches remain outside the installation directory.
