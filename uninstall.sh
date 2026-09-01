#!/bin/bash
set -euo pipefail

remove_marked_block() {
  local file=$1 begin=$2 end=$3 temp
  [[ -f $file ]] || return 0
  temp=$(mktemp)
  sed "/$begin/,/$end/d" "$file" >"$temp"
  mv "$temp" "$file"
}

remove_marked_block "$HOME/.config/hypr/bindings.lua" 'BEGIN omarchy-mac-keybinding' 'END omarchy-mac-keybinding'
remove_marked_block "$HOME/.config/hypr/input.lua" 'BEGIN omarchy-mac-keybinding' 'END omarchy-mac-keybinding'
remove_marked_block "$HOME/.config/omarchy/extensions/omarchy-menu.jsonc" 'BEGIN omarchy-mac-keybinding-menu' 'END omarchy-mac-keybinding-menu'
remove_marked_block "$HOME/.bashrc" 'BEGIN omarchy-mac-keybinding-alias' 'END omarchy-mac-keybinding-alias'

rm -f "$HOME/.local/bin/omarchy-menu-keybindings-mac"
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/omarchy-mac-keys"

omarchy menu refresh >/dev/null 2>&1 || true
hyprctl reload >/dev/null
errors=$(hyprctl configerrors)
[[ -z $errors ]] || { printf 'Hyprland configuration errors:\n%s\n' "$errors" >&2; exit 1; }
printf 'Omarchy Mac keybindings and trackpad customizations removed.\n'
