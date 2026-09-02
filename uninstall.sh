#!/bin/bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
transaction_helper="$repo_dir/scripts/config_transaction.py"
transaction=""
validated=false

rollback_on_failure() {
  local status=$?
  if (( status != 0 )) && [[ -n $transaction && $validated == false ]]; then
    printf 'Removal failed; restoring every changed file...\n' >&2
    python3 "$transaction_helper" rollback "$transaction" || \
      printf 'Automatic rollback failed. Transaction evidence: %s\n' "$transaction" >&2
    hyprctl reload >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap rollback_on_failure EXIT

for command in hyprctl python3; do
  command -v "$command" >/dev/null || { printf 'Missing required command: %s\n' "$command" >&2; exit 1; }
done

transaction=$(python3 "$transaction_helper" uninstall --repo-dir "$repo_dir")

hyprctl reload >/dev/null
errors=$(hyprctl configerrors)
if [[ -n $errors ]]; then
  printf 'Hyprland reported configuration errors:\n%s\n' "$errors" >&2
  exit 1
fi

validated=true
omarchy menu refresh >/dev/null 2>&1 || true
trap - EXIT

printf 'Omarchy Mac keybindings and trackpad customizations removed.\n'
printf 'Transaction and backups: %s\n' "$transaction"
