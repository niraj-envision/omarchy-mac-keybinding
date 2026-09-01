-- BEGIN omarchy-mac-keybinding
hl.config({
  input = {
    touchpad = {
      natural_scroll = true,
      tap_to_click = true,
      tap_and_drag = true,
      drag_lock = 1,
      clickfinger_behavior = true,
      scroll_factor = 0.4,
    },
  },
})

-- Horizontal swipes track workspace movement continuously.
hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })
hl.gesture({ fingers = 4, direction = "horizontal", action = "workspace" })

-- Launchpad-like Apps view and an Omarchy-native Expose alternative.
hl.gesture({
  fingers = 4,
  direction = "up",
  action = function() hl.exec_cmd("omarchy-menu toggle apps") end,
})
hl.gesture({
  fingers = 4,
  direction = "down",
  action = "special",
  workspace_name = "scratchpad",
})
-- END omarchy-mac-keybinding
