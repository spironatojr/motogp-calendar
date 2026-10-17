import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui as Ui

Ui.BarWidget {
    id: root
    moduleName: "local.motogp"
    property string raceLabel: "MotoGP"
    property string raceTooltip: "Open MotoGP race calendar"
    readonly property string runner: decodeURIComponent(String(Qt.resolvedUrl("bin/motogp-calendar")).replace(/^file:\/\//, ""))

    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    Process {
        id: statusProcess
        command: [root.runner, "--status"]
        running: true
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var data = JSON.parse(text)
                    root.raceLabel = data.label
                    root.raceTooltip = data.tooltip
                } catch (error) {
                    root.raceTooltip = "Open MotoGP calendar (status unavailable)"
                }
            }
        }
    }

    Timer {
        interval: 60000
        running: true
        repeat: true
        onTriggered: if (!statusProcess.running) statusProcess.running = true
    }

    Ui.WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: root.vertical ? "" : "  " + root.raceLabel
        tooltipText: root.raceTooltip
        onPressed: function(mouseButton) {
            if (mouseButton === Qt.RightButton)
                Quickshell.execDetached([root.runner, "--official"])
            else
                Quickshell.execDetached([root.runner])
        }
    }
}
