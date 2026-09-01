import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// A small Omarchy-native entry point for the existing, reversible Mac
// keybindings installer. The actual keyboard and trackpad configuration stays
// in the repository's scripts, so this widget never edits user configuration
// itself.
BarWidget {
  id: root
  moduleName: "io.github.niraj-envision.mac-keybindings"

  property bool installed: false

  readonly property string pluginDir: Quickshell.env("HOME")
    + "/.config/omarchy/plugins/io.github.niraj-envision.mac-keybindings"
  readonly property string icon: ""
  readonly property string tooltip: installed
    ? "Open Mac-labelled keybindings"
    : "Install Mac keybindings and trackpad gestures"

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function refresh() {
    if (!statusProbe.running) statusProbe.running = true
  }

  function open() {
    if (!root.bar) return
    if (installed) root.bar.run("omarchy-menu-keybindings-mac")
    else root.install()
  }

  function install() {
    if (!root.bar) return
    root.bar.run("omarchy-launch-floating-terminal-with-presentation "
      + "bash -c '" + root.pluginDir + "/install.sh; read -n 1 -s'")
  }

  Process {
    id: statusProbe
    command: ["sh", "-c",
      "command -v omarchy-menu-keybindings-mac >/dev/null 2>&1 && printf ready || printf setup"]
    running: true
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.installed = String(text || "").trim() === "ready"
    }
  }

  IpcHandler {
    target: "io.github.niraj-envision.mac-keybindings"

    function refresh(): void { root.refresh() }
    function open(): void { root.open() }
    function install(): void { root.install() }
    function status(): string { return root.installed ? "installed" : "setup" }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.vertical ? "" : icon + "  Mac keys"
    labelVisible: !root.vertical
    hasVisualContent: true
    horizontalMargin: 8.75
    verticalPadding: 8.75
    tooltipText: root.tooltip
    active: !root.installed
    activeColor: Color.accent
    foreground: root.bar ? root.bar.barForeground : Color.foreground

    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton) root.refresh()
      else root.open()
    }

    Column {
      visible: root.vertical
      anchors.fill: parent

      OpticalGlyph {
        width: button.width
        height: Style.bar.iconSlot
        text: root.icon
        fontFamily: button.fontFamily
        fontSize: button.fontSize
        color: button.foreground
      }
    }
  }
}
