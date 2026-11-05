"""Bundle only the QML modules used by this application and the Basic style.

Filtering before binary dependency analysis avoids pulling WebEngine/3D into
an application that has no webview or 3D content. Keep this list aligned with
Main.qml and exercise file dialogs in the bundled smoke test.
"""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()
root = Path(pyside6_library_info.location['QmlImportsPath']).resolve()
modules = {
    'QtCore', 'QtQml', 'QtQml/Models', 'QtQml/WorkerScript',
    'QtQuick', 'QtQuick/Window', 'QtQuick/Layouts', 'QtQuick/Templates',
    'QtQuick/Controls', 'QtQuick/Controls/impl', 'QtQuick/Controls/Basic',
    'QtQuick/Controls/Basic/impl', 'QtQuick/Dialogs', 'QtQuick/Dialogs/quickimpl',
    'Qt/labs/folderlistmodel',
}


def needed(item):
    source = Path(item[0])
    relative = (source if source.is_dir() else source.parent).relative_to(root).as_posix()
    return relative in modules or relative.startswith('QtQuick/Dialogs/quickimpl/')


binaries += [item for item in qml_binaries if needed(item)]
datas += [item for item in qml_datas if needed(item)]
