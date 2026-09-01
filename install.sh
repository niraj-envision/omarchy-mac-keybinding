#!/bin/bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-mac-keybinding"
backup_dir="$state_dir/backups/$(date +%Y%m%d-%H%M%S)"
bindings="$HOME/.config/hypr/bindings.lua"
input="$HOME/.config/hypr/input.lua"
menu="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"
bashrc="$HOME/.bashrc"

for command in hyprctl python3 sed; do
  command -v "$command" >/dev/null || { printf 'Missing required command: %s\n' "$command" >&2; exit 1; }
done

for file in "$bindings" "$input" "$menu"; do
  [[ -f $file ]] || { printf 'Expected Omarchy config not found: %s\n' "$file" >&2; exit 1; }
done

mkdir -p "$backup_dir" "$HOME/.local/bin"
cp "$bindings" "$input" "$menu" "$backup_dir/"
[[ -f $bashrc ]] && cp "$bashrc" "$backup_dir/bashrc"

remove_marked_block() {
  local file=$1 begin=$2 end=$3 temp
  temp=$(mktemp)
  sed "/$begin/,/$end/d" "$file" >"$temp"
  mv "$temp" "$file"
}

install_snippet() {
  local destination=$1 snippet=$2
  remove_marked_block "$destination" 'BEGIN omarchy-mac-keybinding' 'END omarchy-mac-keybinding'
  printf '\n' >>"$destination"
  sed -n '/BEGIN omarchy-mac-keybinding/,/END omarchy-mac-keybinding/p' "$snippet" >>"$destination"
}

install -m 0755 "$repo_dir/bin/omarchy-menu-keybindings-mac" "$HOME/.local/bin/omarchy-menu-keybindings-mac"
install_snippet "$bindings" "$repo_dir/config/bindings.lua"
install_snippet "$input" "$repo_dir/config/input.lua"

python3 - "$menu" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
s = re.sub(r'\n?\s*// BEGIN omarchy-mac-keybinding-menu.*?// END omarchy-mac-keybinding-menu\n?', '\n', s, flags=re.S)
block = '''
  // BEGIN omarchy-mac-keybinding-menu
  // Display MacBook modifier names in Learn -> Keybindings.
  "learn.keybindings": {"icon":"","label":"Keybindings","action":"~/.local/bin/omarchy-menu-keybindings-mac"},
  // END omarchy-mac-keybinding-menu
'''
i = s.rstrip().rfind('}')
if i < 0:
    raise SystemExit(f'Could not find closing object in {p}')
p.write_text(s[:i] + block + s[i:])
PY

if [[ -f $bashrc ]]; then
  remove_marked_block "$bashrc" 'BEGIN omarchy-mac-keybinding-alias' 'END omarchy-mac-keybinding-alias'
  cat >>"$bashrc" <<'EOF'

# BEGIN omarchy-mac-keybinding-alias
alias omarchy-menu-keybindings="$HOME/.local/bin/omarchy-menu-keybindings-mac"
# END omarchy-mac-keybinding-alias
EOF
fi

omarchy menu refresh >/dev/null 2>&1 || true
hyprctl reload >/dev/null
errors=$(hyprctl configerrors)
if [[ -n $errors ]]; then
  printf 'Hyprland reported configuration errors:\n%s\n' "$errors" >&2
  printf 'Backups: %s\n' "$backup_dir" >&2
  exit 1
fi

printf 'Installed successfully. Backups: %s\n' "$backup_dir"
printf 'Try Command+K, Command+A, Command+Z, and three-finger horizontal swipe.\n'
