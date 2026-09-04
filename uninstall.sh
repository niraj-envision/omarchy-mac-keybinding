#!/bin/bash
set -euo pipefail

script_path=${BASH_SOURCE[0]}
[[ $script_path == /* ]] || script_path=$PWD/$script_path
repo_dir=$(cd -- "${script_path%/*}" && pwd -P)
transaction_helper="$repo_dir/scripts/config_transaction.py"
python_bin=/usr/bin/python3
hyprctl_bin=/usr/bin/hyprctl
omarchy_bin=/usr/bin/omarchy
transaction=""
validated=false

rollback_on_failure() {
  local status=$?
  if (( status != 0 )) && [[ -n $transaction && $validated == false ]]; then
    printf 'Removal failed; restoring every changed file...\n' >&2
    "$python_bin" "$transaction_helper" rollback "$transaction" || \
      printf 'Automatic rollback failed. Transaction evidence: %s\n' "$transaction" >&2
    "$hyprctl_bin" reload >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap rollback_on_failure EXIT

for command in "$python_bin" "$hyprctl_bin"; do
  [[ -x $command ]] || { printf 'Missing required command: %s\n' "$command" >&2; exit 1; }
done

transaction=$("$python_bin" "$transaction_helper" uninstall --repo-dir "$repo_dir")

"$hyprctl_bin" reload >/dev/null
errors=$("$hyprctl_bin" configerrors)
if [[ -n $errors ]]; then
  printf 'Hyprland reported configuration errors:\n%s\n' "$errors" >&2
  exit 1
fi

validated=true
[[ ! -x $omarchy_bin ]] || "$omarchy_bin" menu refresh >/dev/null 2>&1 || true
trap - EXIT

printf 'Omarchy Mac keybindings and trackpad customizations removed.\n'
printf 'Transaction and backups: %s\n' "$transaction"
