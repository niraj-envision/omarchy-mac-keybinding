-- BEGIN omarchy-mac-keybinding
-- Display MacBook modifier names in the keybindings menu. Display only:
-- Hyprland still receives Command as SUPER, Option as ALT, and Control as CTRL.
hl.unbind("SUPER + K")
o.bind("SUPER + K", "Keybindings", "~/.local/bin/omarchy-menu-keybindings-mac")

-- Send Linux-standard Control editing chords while the physical Command key
-- remains held. Explicit down/up events avoid stuck synthetic key states.
local function omarchy_mac_edit_shortcut(key)
  return function()
    hl.dispatch(hl.dsp.send_key_state({ mods = "CTRL", key = key, state = "down" }))

    hl.timer(function()
      hl.dispatch(hl.dsp.send_key_state({ mods = "CTRL", key = key, state = "up" }))
    end, { timeout = 50, type = "oneshot" })
  end
end

o.bind("SUPER + A", "Select all", omarchy_mac_edit_shortcut("A"))
o.bind("SUPER + Z", "Undo", omarchy_mac_edit_shortcut("Z"))
-- END omarchy-mac-keybinding
