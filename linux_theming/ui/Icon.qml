import QtQuick
import QtQuick.Controls.impl

// Monochrome line icon from ./icons, tinted with `color`.
ColorImage {
    property string name: ""
    property int size: 16
    source: name ? Qt.resolvedUrl("icons/" + name + ".svg") : ""
    sourceSize: Qt.size(size, size)
    width: size
    height: size
    color: Theme.text
    Accessible.ignored: true
}
