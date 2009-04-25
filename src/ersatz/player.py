#!/usr/bin/env python

# Copyright 2009  Carlos Corbacho <carlos@strangeworlds.co.uk>

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of
# the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


# TODO:
# * Keyboard bindings
# * Playlist filter
# * Clear playlist
# * Video in playlist view

import copy
import mimetypes
import os
import sys
import urllib

from PyKDE4 import kdecore
from PyKDE4 import phonon
from PyKDE4 import kdeui
from PyQt4 import QtGui
from PyQt4 import QtCore


class PlaylistItem(object):

    def __init__(self):
        self.file = None

    def _get_file(self):
        return self._file

    def _set_file(self, file):
        if file is not None:
            self.title = os.path.basename(file)
        self._file = file

    file = property(_get_file, _set_file)


class PlaylistDelegate(QtGui.QItemDelegate):

    def __init__(self, parent=None):
        super(PlaylistDelegate, self).__init__(parent)

    def paint(self, painter, option, index):
        print "paint"
        option.showDecorationSelected = True
        print type(painter)
        QtGui.QItemDelegate.paint(self, painter, option, index)


class PlaylistModel(QtCore.QAbstractTableModel):

    FILE, TITLE = range(2)
    ActiveTrackRole = QtCore.Qt.UserRole + 1 # TODO - faily

    def __init__(self, parent=None):
        super(PlaylistModel, self).__init__(parent)
        self.media_file_extensions = self._get_file_extensions()
        self.playlist = []
        self.active_track_row = -1

    def _get_file_extensions(self):
        file_extensions = []
        available_mimetypes = (
            unicode(mimetype) for mimetype in
            phonon.Phonon.BackendCapabilities.availableMimeTypes())
        for mimetype in available_mimetypes:
            if mimetype.startswith("image") or mimetype.startswith("audio"):
                continue
            extensions = mimetypes.guess_all_extensions(mimetype)
            if len(extensions) == 0:
                continue
            file_extensions.extend(extensions)
        return file_extensions

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if (role == self.ActiveTrackRole):
            return QtCore.QVariant(index.row() == self.active_track_row)
        if (not index.isValid() or
            not (0 <= index.row() < len(self.playlist))):
                return QtCore.QVariant()
        playlist_item = self.playlist[index.row()]
        column = index.column()
        if role == QtCore.Qt.DisplayRole:
            if column == self.FILE:
                return QtCore.QVariant(playlist_item.file)
            elif column == self.TITLE:
                return QtCore.QVariant(playlist_item.title)
        return QtCore.QVariant()

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.TextAlignmentRole:
            if orientation == QtCore.Qt.Horizontal:
                return QtCore.QVariant(
                    int(QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter))
            return QtCore.QVariant(
                int(QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter))
        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()
        if orientation == QtCore.Qt.Horizontal:
            if section == self.FILE:
                return QtCore.QVariant("File")
            elif section == self.TITLE:
                return QtCore.QVariant("Title")
        return QtCore.QVariant(int(section + 1))

    def rowCount(self, index=QtCore.QModelIndex()):
        return len(self.playlist)

    def columnCount(self, index=QtCore.QModelIndex()):
        return 2

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if role == self.ActiveTrackRole:
            self.active_track_row = index.row()
            return True
        if index.isValid() and 0 <= index.row() < len(self.playlist):
            playlist_item = self.playlist[index.row()]
            column = index.column()
            if column == self.FILE:
                playlist_item.file = unicode(value.toString())
            self.emit(
                QtCore.SIGNAL("dataChanged(const QModelIndex &, "
                              "const QModelIndex &)"), index, index)
            return True
        return False

    def insertRows(self, position, rows=1, index=QtCore.QModelIndex()):
        self.beginInsertRows(QtCore.QModelIndex(), position,
                             position + rows - 1)
        for row in range(rows):
            self.playlist.insert(position + row,
                                 PlaylistItem())
        self.endInsertRows()

    def removeRows(self):
        pass

    def _visitor(self, arg, dirname, names):
        for file in sorted(names):
            if os.path.isdir(file):
                os.path.walk(file, self._visitor, self.row)
            extension = os.path.splitext(file)[-1]
            if extension in self.media_file_extensions:
                self._insert_file(os.path.join(dirname, file))

    def _insert_file(self, file):
        if os.path.isdir(file):
            os.path.walk(file, self._visitor, None)
            return
        self.insertRows(self.row)
        self.setData(
            self.index(self.row, PlaylistModel.FILE),
            QtCore.QVariant(file))
        QtCore.QCoreApplication.processEvents()
        self.row += 1

    def dropMimeData(self, data, action, row, column, parent):
        if action == QtCore.Qt.IgnoreAction:
            return True
        if not data.hasFormat("text/uri-list"):
            return False

        if row != -1:
            start_row = row
        elif parent.isValid():
            start_row = parent.row()
        else:
            start_row = self.rowCount()

        raw_data = data.data("text/uri-list")
        files = [urllib.unquote(file.replace("file://", "")) for file in
                 unicode(raw_data).strip().split()]
        # TODO - rethink this
        self.row = start_row
        for file in files:
            self._insert_file(file)
        return True

    def flags(self, index):
        default_flags = QtCore.QAbstractTableModel.flags(self, index)
        if index.isValid():
            return QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled | default_flags
        else:
            return QtCore.Qt.ItemIsDropEnabled | default_flags

    def supportedDropActions(self):
        return QtCore.Qt.CopyAction

    def mimeTypes(self):
        return ["text/uri-list"]

    def clear(self):
        self.playlist = []
        self.active_track_row = -1
        self.reset()


class SimpleDirModel(QtGui.QDirModel):

    def __init__(self, parent=None, filter=None):
        super(SimpleDirModel, self).__init__(parent)
        self.setReadOnly(True)
        self.setLazyChildCount(True)
        self.setFilter(
            QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot |
            QtCore.QDir.Files)
        self.setNameFilters(filter)

    def columnCount(self, index=QtCore.QModelIndex()):
        return 1


class MediaPlayer(kdeui.KMainWindow):

    def __init__(self, parent=None):
        super(MediaPlayer, self).__init__(parent)

        self.action_collection = kdeui.KActionCollection(self)
        self._setup_widgets()
        self._setup_menus()
        self._setup_toolbars()
        self.current_index = None
        self.playlist_delegate = PlaylistDelegate()

    def _setup_player(self):
        pass

    def _setup_playlist(self):
        pass

    # TODO - split this up
    def _setup_widgets(self):
        self.playlist_view = QtGui.QTableView()
        self.playlist_view.setAcceptDrops(True)
        self.playlist_view.setDragEnabled(True)
        self.playlist_view.setDropIndicatorShown(True)
        self.playlist_view.setAlternatingRowColors(True)
#        self.playlist_view.setDragDropMode(QtGui.QAbstractItemView.DropOnly)
        self.playlist_model = PlaylistModel()

        self.playlist_view.setModel(self.playlist_model)
        self.playlist_view.resizeRowsToContents()
        self.playlist_view.hideColumn(PlaylistModel.FILE)
        self.playlist_view.setAlternatingRowColors(True)
        self.playlist_view.horizontalHeader().resizeSections(
            QtGui.QHeaderView.Stretch)
#        self.playlist_view.setUniformRowHeights(True)
        self.connect(
            self.playlist_view, QtCore.SIGNAL("doubleClicked(QModelIndex)"),
            self.play)
        self.video_widget = phonon.Phonon.VideoWidget()
        self.audio_output = phonon.Phonon.AudioOutput()
        self.media_object = phonon.Phonon.MediaObject()

        self.connect(
            self.media_object, QtCore.SIGNAL("aboutToFinish()"),
            self.queue_next_track)

        self.connect(
            self.media_object,
            QtCore.SIGNAL("currentSourceChanged(const Phonon::MediaSource &)"),
            self.update_title)

        self.dir_view = QtGui.QTreeView()
        self.dir_view.setSelectionMode(
            QtGui.QAbstractItemView.ContiguousSelection)
        media_filter = ["*%s" % extension for extension in
                        self.playlist_model.media_file_extensions]
        self.dir_model = SimpleDirModel(filter=media_filter)
        self.dir_view.setModel(self.dir_model)
        self.dir_view.setDragEnabled(True)

        phonon.Phonon.createPath(self.media_object, self.video_widget)
        phonon.Phonon.createPath(self.media_object, self.audio_output)

        self.tab_widget = QtGui.QTabWidget()
        self.tab_widget.setTabPosition(QtGui.QTabWidget.West)

        self.player_widget = QtGui.QWidget()
        self.player_layout = QtGui.QHBoxLayout()
        self.player_layout.addWidget(self.video_widget)
        self.player_widget.setLayout(self.player_layout)
        self.tab_widget.addTab(self.player_widget, "Player Window")

        self.playlist_widget = QtGui.QWidget()
        self.playlist_layout = QtGui.QHBoxLayout()
        self.playlist_widget.setLayout(self.playlist_layout)
        self.playlist_layout.addWidget(self.dir_view)
        self.playlist_layout.addWidget(self.playlist_view)

        self.dir_widget = QtGui.QWidget()
        self.dir_layout = QtGui.QVBoxLayout()
        self.dir_widget.setLayout(self.dir_layout)
        self.dir_layout.addWidget(self.dir_view)
#        self.dir_layout.addWidget(self.playlist_video_widget)
        self.splitter = QtGui.QSplitter(QtCore.Qt.Horizontal)
#        self.splitter.addWidget(self.dir_view)
        self.splitter.addWidget(self.dir_widget)
        self.splitter.addWidget(self.playlist_view)
        self.tab_widget.addTab(self.splitter, "Playlist")
        self.setCentralWidget(self.tab_widget)

    def _setup_menus(self):
        player_menu = self.menuBar().addMenu("&Player")
        open_action = self._add_action("Open", icon="document-open")
        player_menu.addAction(open_action)
        playlist_menu = self.menuBar().addMenu("Play&list")
        playlist_toolbar = self.addToolBar("Playlist")
        add_media_action = self._add_action("Add Media", self._add_media)
        clear_playlist_action = self._add_action(
            "&Clear playlist", self.playlist_model.clear)
        playlist_menu.addAction(add_media_action)
        playlist_menu.addAction(clear_playlist_action)
        settings_menu = self.menuBar().addMenu("&Settings")
        settings_menu.addAction(
            kdeui.KStandardAction.keyBindings(
                self, QtCore.SLOT("configure_shortcuts()"),
                self.action_collection))

        open_action = self._add_action("Open", icon="document-open")
        player_menu.addAction(open_action)

    @QtCore.pyqtSignature("")
    def configure_shortcuts(self):
        kdeui.KShortcutsDialog.configure(self.action_collection)

    def _setup_toolbars(self):
        controls_toolbar = self.addToolBar("Controls")

        previous_action = self._add_action(
            "Previous", self.previous, "media-skip-backward")
        self.play_pause_action = self._add_action(
            "Play", self.media_object.play, "media-playback-start",
            QtCore.Qt.Key_Space)
        stop_action = self._add_action(
            "Stop", self.media_object.stop, "media-playback-stop")
        # TODO - plug up to something
        next_action = self._add_action(
            "Next", self.next, "media-skip-forward")

        self.connect(self.media_object,
                     QtCore.SIGNAL("stateChanged(Phonon::State, Phonon::State)"),
                     self.play_pause)

        controls_toolbar.addAction(previous_action)
        controls_toolbar.addAction(self.play_pause_action)
        controls_toolbar.addAction(stop_action)
        controls_toolbar.addAction(next_action)

        volume_toolbar = self.addToolBar("Volume")
        volume_action = kdeui.KAction("Volume", self)
        volume_slider = phonon.Phonon.VolumeSlider()
        volume_slider.setMuteVisible(True)
        volume_slider.setAudioOutput(self.audio_output)
        volume_action.setDefaultWidget(volume_slider)
        volume_toolbar.addAction(volume_action)

        position_toolbar = self.addToolBar("Position")
        position_action = kdeui.KAction("Position", self)
        position_slider = phonon.Phonon.SeekSlider()
        position_slider.setMediaObject(self.media_object)
        position_action.setDefaultWidget(position_slider)
        position_toolbar.addAction(position_action)

    def _add_action(self, text, slot=None, icon=None, shortcut=None,
                    signal="triggered()"):
        action = kdeui.KAction(text, self)
        if slot is not None:
            self.connect(action, QtCore.SIGNAL(signal), slot)
        if icon is not None:
            action.setIcon(kdeui.KIcon(icon))
        if shortcut is not None:
            action.setShortcut(shortcut)
        self.action_collection.addAction(text, action)
        return action

    def _add_media(self):
        # TODO - can we just show media files here?
        files = QtGui.QFileDialog().getOpenFileNames(self, "Add Media")
        for file in files:
            row = self.playlist_model.rowCount()
            self.playlist_model.insertRows(row)
            self.playlist_model.setData(
                self.playlist_model.index(row, PlaylistModel.FILE),
                QtCore.QVariant(file))
            index = self.playlist_model.index(row, 0)
        self.playlist_view.resizeRowsToContents()

    def play_pause(self, new_state, old_state):
        if new_state in [phonon.Phonon.PausedState, phonon.Phonon.ErrorState,
                         phonon.Phonon.StoppedState]:
            self.play_pause_action.setIcon(kdeui.KIcon("media-playback-start"))
            self.connect(self.play_pause_action, QtCore.SIGNAL("triggered()"),
                         self.media_object.play)
        else:
            self.play_pause_action.setIcon(kdeui.KIcon("media-playback-pause"))
            self.connect(self.play_pause_action, QtCore.SIGNAL("triggered()"),
                         self.media_object.pause)

    def play(self, index):
        if index.isValid():
            selected_row = index.row()
        elif self.playlist_model.rowCount() > 0:
            # TODO - be smarter
            selected_row = 0
        else:
            # TODO - should we do something better here?
            return
        file_index = self.playlist_model.createIndex(
            selected_row, PlaylistModel.FILE)
        self.playlist_model.setData(
            file_index, None, PlaylistModel.ActiveTrackRole)
        file = self.playlist_model.data(file_index).toString()
        self.current_index = file_index
        media_source = phonon.Phonon.MediaSource(file)
        self.media_object.setCurrentSource(media_source)
        self.media_object.play()

    def next(self):
        next_index = self.playlist_model.createIndex(
            self.playlist_model.active_track_row + 1,
            self.current_index.column())
        self.play(next_index)

    def previous(self):
        previous_index = self.playlist_model.createIndex(
            self.playlist_model.active_track_row - 1,
            self.current_index.column())
        self.play(previous_index)

    def queue_next_track(self):
        next_index = self.playlist_model.createIndex(
            self.playlist_model.active_track_row + 1, PlaylistModel.FILE)
        if not next_index.isValid():
            return
        file = self.playlist_model.data(next_index).toString()
        print file
        media_source = phonon.Phonon.MediaSource(file)
        self.media_object.enqueue(media_source)

    def update_title(self, source):
        file = os.path.split(unicode(source.url().toString()))[-1]
        self.setWindowTitle(u"%s - Ersatz" % file)


def get_about_data():
    app_name = "ersatz"
    catalog = ""
    program_name = kdecore.ki18n("Ersatz")
    version = "0.1"
    description = kdecore.ki18n("A simple Media Player")
    license = kdecore.KAboutData.License_GPL
    copyright = kdecore.ki18n("(c) 2009 Carlos Corbacho")
    text = kdecore.ki18n("none")
    home_page = "www.strangeworlds.co.uk"
    bug_email = "carlos@strangeworlds.co.uk"
    return kdecore.KAboutData(
        app_name, catalog, program_name, version, description, license,
        copyright, text, home_page, bug_email)


def main(argv):
    about_data = get_about_data()
    kdecore.KCmdLineArgs.init(argv, about_data)
    app = kdeui.KApplication()
    player = MediaPlayer()
    player.show()
    app.exec_()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
