# Omarchy Mac keybindings and trackpad

MacBook-friendly keyboard labels, editing shortcuts, and trackpad gestures for
[Omarchy](https://omarchy.org/) on Hyprland 0.55 or newer.

This project does **not** remap the physical keyboard. On Linux, the Mac
Command key is reported to Hyprland as `SUPER`, Option as `ALT`, and Control as
`CTRL`. The configuration keeps those real modifier names internally and only
shows their Mac names in Omarchy's keybindings menu.

## Features

### Keyboard

- Omarchy's keybindings menu displays `COMMAND`, `OPTION`, and `CONTROL`
- `Command + A` sends `Control + A` (Select all)
- `Command + Z` sends `Control + Z` (Undo)
- Omarchy's existing universal shortcuts continue to provide Command+C/V/X
- `Command + K` opens the Mac-labelled keybindings menu

### Trackpad

- Natural two-finger scrolling
- Tap to click and tap-and-drag with a short drag lock
- Two-finger click for right-click (clickfinger behavior)
- Three- or four-finger horizontal swipe switches workspaces/desktops
- Four-finger swipe up opens the Apps menu
- Four-finger swipe down toggles the scratchpad workspace
- Two-finger pinch remains available to applications for page/map zoom

## Requirements

- Omarchy with its Lua-based Hyprland configuration (Hyprland 0.55+)
- Bash, `sed`, and `python3`

The configuration was created and tested on a 2018 Intel MacBook Pro running
Hyprland 0.56.2.

## Install

```bash
git clone https://github.com/niraj-envision/omarchy-mac-keybinding.git
cd omarchy-mac-keybinding
./install.sh
```

The installer:

1. Copies the menu wrapper to `~/.local/bin/`
2. Adds marked blocks to `~/.config/hypr/bindings.lua` and `input.lua`
3. Overrides the Omarchy Learn → Keybindings menu action
4. Adds a Bash alias for the Mac-labelled terminal command
5. Reloads and validates Hyprland

Configuration changes are performed as one locked transaction. The installer
verifies parent directories and target ownership/type/mode, rejects malformed
or duplicate markers, preserves file modes, writes and fsyncs exclusive
same-directory temporary files, detects concurrent changes, and atomically
replaces each target. Originals and the transaction journal are retained under
`~/.local/state/omarchy-mac-keybinding/transactions/`. If any write or the
Hyprland validation fails, every completed change is automatically rolled back.
Running the installer again updates the exact managed blocks without duplicates.

## Usage

Press `Command + K`, open **Omarchy → Learn → Keybindings**, or run:

```bash
omarchy-menu-keybindings-mac
omarchy-menu-keybindings-mac --print
```

## Customize

The installable snippets are in [`config/`](config/):

- [`bindings.lua`](config/bindings.lua) — keyboard shortcuts
- [`input.lua`](config/input.lua) — touchpad settings and gestures

For example, change `scroll_factor = 0.4` to make scrolling faster or slower.
After editing an installed Hyprland file, validate it with:

```bash
hyprctl reload
hyprctl configerrors
```

## Uninstall

```bash
./uninstall.sh
```

Removal uses the same locked transaction and rollback guarantees. It removes
only exact, structurally valid managed blocks and the installed wrapper while
preserving other personal Omarchy settings.

## Notes

- Hyprland has no built-in macOS Mission Control clone. The Apps menu and
  scratchpad are stable Omarchy-native alternatives for four-finger vertical
  gestures.
- Omarchy package files under `/usr/share/omarchy` are never modified, so an
  Omarchy update will not overwrite this customization.
- The keybindings wrapper regenerates its cached copy whenever Omarchy updates
  the packaged keybindings menu.

## License

MIT
