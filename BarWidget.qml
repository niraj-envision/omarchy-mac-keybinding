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

  readonly property string installPath: Qt.resolvedUrl("install.sh").toString().replace(/^file:\/\//, "")
  readonly property string installedPath: Quickshell.env("HOME") + "/.local/bin/omarchy-menu-keybindings-mac"
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
    if (installed) {
      if (!menuProc.running) menuProc.running = true
    }
    else root.install()
  }

  function install() {
    if (!installerProc.running) installerProc.running = true
  }

  Process {
    id: statusProbe
    command: ["/usr/bin/test", "-x", root.installedPath]
    running: true
    onExited: function(exitCode, exitStatus) { root.installed = exitCode === 0 }
  }

  Timer {
    interval: 2000
    repeat: false
    running: statusProbe.running
    onTriggered: {
      statusProbe.running = false
      root.installed = false
    }
  }

  Process {
    id: menuProc
    command: [root.installedPath]
  }

  Process {
    id: installerProc
    command: [
      "/usr/bin/setsid", "/usr/bin/uwsm-app", "--", "/usr/bin/xdg-terminal-exec",
      "--app-id=org.omarchy.terminal", "--title=Mac Keybindings Setup",
      "-e", "/bin/bash", root.installPath
    ]
    onExited: function(exitCode, exitStatus) { root.refresh() }
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
