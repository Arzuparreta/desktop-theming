import QtQuick
import QtQuick.Layouts

// Small status label. Tones: neutral, accent, warning, danger, info, faint.
Rectangle {
    id: chip
    property string text: ""
    property string tone: "neutral"
    property string iconName: ""
    readonly property color foreground: ({ accent: Theme.accent, warning: Theme.warning, danger: Theme.danger,
                                           info: Theme.info, faint: Theme.textFaint })[tone] || Theme.textMuted
    implicitHeight: 22
    implicitWidth: row.implicitWidth + 16
    radius: 11
    color: ({ accent: Theme.accentSoft, warning: Theme.warningSoft, danger: Theme.dangerSoft,
              info: Theme.infoSoft, faint: "transparent" })[tone] || Theme.raised
    border.width: 1
    border.color: ({ accent: Theme.accentBorder, warning: Theme.warningBorder, danger: Theme.dangerBorder,
                     info: Theme.infoBorder })[tone] || Theme.border
    Accessible.role: Accessible.StaticText
    Accessible.name: text
    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 5
        Icon { visible: !!chip.iconName; name: chip.iconName; size: 12; color: chip.foreground }
        Text { text: chip.text; color: chip.foreground; font.pixelSize: Theme.caption; textFormat: Text.PlainText }
    }
}
