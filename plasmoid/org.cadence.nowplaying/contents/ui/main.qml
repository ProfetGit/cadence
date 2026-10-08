import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PC3
import org.kde.kirigami as Kirigami
import org.kde.plasma.private.mpris as Mpris
import org.kde.plasma.plasma5support as P5Support

PlasmoidItem {
    id: root

    readonly property string playerName: "Cadence"
    readonly property var player: mpris.currentPlayer
    readonly property bool active: !!player && player.identity === playerName
    readonly property bool playing: active && player.playbackStatus === Mpris.PlaybackStatus.Playing
    readonly property string title: active ? player.track : ""
    readonly property string artist: active ? player.artist : ""
    readonly property string artUrl: active ? player.artUrl : ""

    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground | PlasmaCore.Types.ConfigurableBackground
    toolTipMainText: active && title ? title : "Cadence"
    toolTipSubText: active ? artist : "Not running"

    function pick() {
        for (let i = 1; i < mpris.rowCount(); i++) {
            const p = mpris.data(mpris.index(i, 0), Qt.UserRole + 1)
            if (p && p.identity === playerName) {
                if (mpris.currentIndex !== i) mpris.currentIndex = i
                return
            }
        }
    }

    Mpris.Mpris2Model {
        id: mpris
        onRowsInserted: root.pick()
        onRowsRemoved: root.pick()
        Component.onCompleted: root.pick()
    }

    P5Support.DataSource {
        id: launcher
        engine: "executable"
        connectedSources: []
        onNewData: (source) => disconnectSource(source)
        function run(cmd) { connectSource(cmd) }
    }

    Timer {
        interval: 1000
        repeat: true
        running: root.playing
        onTriggered: root.player.updatePosition()
    }

    function fmt(us) {
        const s = Math.max(0, Math.floor(us / 1000000))
        return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0")
    }

    compactRepresentation: MouseArea {
        Layout.minimumWidth: row.implicitWidth + Kirigami.Units.largeSpacing
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        onClicked: (m) => {
            if (!root.active) launcher.run("cadence")
            else if (m.button === Qt.MiddleButton) root.player.PlayPause()
            else root.expanded = !root.expanded
        }
        RowLayout {
            id: row
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing
            Kirigami.Icon { source: root.playing ? "media-playback-start" : "cadence"; Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium; Layout.preferredHeight: Layout.preferredWidth }
            PC3.Label {
                visible: Plasmoid.formFactor === PlasmaCore.Types.Horizontal
                text: root.active && root.title ? (root.artist ? root.artist + " — " : "") + root.title : "Cadence"
                elide: Text.ElideRight
                Layout.maximumWidth: Kirigami.Units.gridUnit * 14
            }
        }
    }

    fullRepresentation: Item {
        id: card
        implicitWidth: Kirigami.Units.gridUnit * 22
        implicitHeight: Kirigami.Units.gridUnit * 9
        Layout.minimumWidth: Kirigami.Units.gridUnit * 16
        Layout.minimumHeight: Kirigami.Units.gridUnit * 7

        Rectangle {
            anchors.fill: parent
            radius: Kirigami.Units.gridUnit * 1.1
            color: Qt.rgba(Kirigami.Theme.backgroundColor.r, Kirigami.Theme.backgroundColor.g, Kirigami.Theme.backgroundColor.b, 0.72)
            border.width: 1
            border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.14)
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing * 1.2
            spacing: Kirigami.Units.largeSpacing * 1.2
            visible: root.active

            Kirigami.ShadowedImage {
                id: cover
                Layout.preferredWidth: Math.min(card.height - Kirigami.Units.largeSpacing * 2.4, card.width * 0.4)
                Layout.preferredHeight: Layout.preferredWidth
                Layout.alignment: Qt.AlignVCenter
                radius: Kirigami.Units.gridUnit * 0.7
                source: root.artUrl
                color: Kirigami.Theme.alternateBackgroundColor
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: if (root.player.canRaise) root.player.Raise() }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0
                Item { Layout.fillHeight: true }
                PC3.Label {
                    Layout.fillWidth: true
                    text: root.title || "Nothing playing"
                    font.bold: true
                    font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.2
                    elide: Text.ElideRight
                }
                PC3.Label {
                    Layout.fillWidth: true
                    text: root.artist
                    opacity: 0.65
                    elide: Text.ElideRight
                }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    spacing: Kirigami.Units.smallSpacing
                    PC3.ToolButton { icon.name: "media-skip-backward"; enabled: root.active && root.player.canGoPrevious; onClicked: root.player.Previous() }
                    PC3.ToolButton {
                        icon.name: root.playing ? "media-playback-pause" : "media-playback-start"
                        enabled: root.active && (root.playing ? root.player.canPause : root.player.canPlay)
                        onClicked: root.player.PlayPause()
                    }
                    PC3.ToolButton { icon.name: "media-skip-forward"; enabled: root.active && root.player.canGoNext; onClicked: root.player.Next() }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    PC3.Label { text: root.active ? root.fmt(root.player.position) : "0:00"; opacity: 0.6; font.pointSize: Kirigami.Theme.smallFont.pointSize }
                    PC3.Slider {
                        Layout.fillWidth: true
                        from: 0
                        to: root.active ? Math.max(1, root.player.length) : 1
                        value: root.active ? root.player.position : 0
                        enabled: root.active && root.player.canSeek
                        onMoved: root.player.position = value
                    }
                    PC3.Label { text: root.active ? root.fmt(root.player.length) : "0:00"; opacity: 0.6; font.pointSize: Kirigami.Theme.smallFont.pointSize }
                }
                Item { Layout.fillHeight: true }
            }
        }

        ColumnLayout {
            anchors.centerIn: parent
            spacing: Kirigami.Units.largeSpacing
            visible: !root.active
            Kirigami.Icon { source: "cadence"; Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: Kirigami.Units.iconSizes.huge; Layout.preferredHeight: Layout.preferredWidth }
            PC3.Label { text: "Cadence isn't running"; Layout.alignment: Qt.AlignHCenter; opacity: 0.7 }
            PC3.Button { text: "Start Cadence"; icon.name: "media-playback-start"; Layout.alignment: Qt.AlignHCenter; onClicked: launcher.run("cadence --hidden") }
        }
    }
}
