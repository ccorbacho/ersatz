#!/usr/bin/env python

# Copyright 2009-2011  Carlos Corbacho <carlos@strangeworlds.co.uk>

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
# * Video in playlist view

import copy
import mimetypes
import os
import Queue
import threading
import sys
import urllib

from PyKDE4 import kdecore
from PyKDE4 import kdeui
from PyQt4 import phonon
from PyQt4 import QtGui
from PyQt4 import QtCore


class PopulatePlaylist(threading.Thread):

    def __init__(self, playlist_model, queue, **kwargs):
        self._playlist_model = playlist_model
        self._queue = queue
        super(PopulatePlaylist, self).__init__(**kwargs)

    def run(self):
        row, items = self._queue.get()
        for item in items:
            if os.path.isdir(item.decode("utf-8")):
                row = self._visitor(row, item, os.listdir(item))
                continue
            else:
                self._insert_file(row, item)

    def _visitor(self, row, directory, names):
        for name in sorted(names):
            name_path = os.path.join(directory, name)
            if os.path.isdir(name_path):
                row = self._visitor(row, name_path, os.listdir(name_path))
                continue
            extension = os.path.splitext(name)[-1]
            if extension in self._playlist_model.media_file_extensions:
                self._insert_file(row, name_path)
                row += 1
        return row

    def _insert_file(self, row, file_):
        QtCore.QCoreApplication.processEvents()
        QtCore.QCoreApplication.sendPostedEvents()
        self._playlist_model.insertRows(row)
        self._playlist_model.setData(
            self._playlist_model.index(row, PlaylistModel.FILE),
            QtCore.QVariant(file_))


class PlaylistItem(object):

    def __init__(self):
        self._file = None

    @property
    def file(self):
        return self._file

    @file.setter
    def file(self, file_):
        self._file = file_

    @property
    def title(self):
        if self.file is not None:
            return os.path.basename(self.file)


class PlaylistDelegate(QtGui.QItemDelegate):

    def __init__(self, parent=None):
        super(PlaylistDelegate, self).__init__(parent)

    def paint(self, painter, option, index):
        option.showDecorationSelected = True
        QtGui.QItemDelegate.paint(self, painter, option, index)


class PlaylistModel(QtCore.QAbstractTableModel):

    FILE, TITLE = range(2)
    ActiveTrackRole = QtCore.Qt.UserRole + 1 # TODO - faily

    def __init__(self, parent=None):
        super(PlaylistModel, self).__init__(parent)
        self.media_file_extensions = self._get_file_extensions()
        self.playlist = []
        self.active_track_row = -1
        self._queue = Queue.Queue()
        self._populate_thread = PopulatePlaylist(self, self._queue)
        self._populate_thread.daemon = True
        self._populate_thread.start()

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
            self.playlist.insert(position + row, PlaylistItem())
        self.endInsertRows()

    def removeRows(self):
        pass

    def dropMimeData(self, data, action, row, column, parent):
        if action == QtCore.Qt.IgnoreAction:
            return True
        if not data.hasFormat("text/uri-list"):
            return False
        row = 0
        if parent.row() != -1:
            row = parent.row()
        raw_data = data.data("text/uri-list")
        files = [urllib.unquote(file_.replace("file://", "")) for file_ in
                 unicode(raw_data).strip().split()]
        self._queue.put((row, files))
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

    def __init__(self, parent=None, filter_=None):
        super(SimpleDirModel, self).__init__(parent)
        self.setReadOnly(True)
        self.setLazyChildCount(True)
        self.setFilter(
            QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot |
            QtCore.QDir.Files)
        self.setNameFilters(filter_)

    def columnCount(self, index=QtCore.QModelIndex()):
        return 1


class MediaPlayer(kdeui.KMainWindow):

    NOT_PLAYING_STATES = set([
            phonon.Phonon.PausedState, phonon.Phonon.ErrorState,
            phonon.Phonon.StoppedState])

    def __init__(self, parent=None):
        super(MediaPlayer, self).__init__(parent)
        self.action_collection = kdeui.KActionCollection(self)
        self._setup_player()
        self._setup_playlist()
        self._setup_widgets()
        self._setup_menus()
        self._setup_toolbars()
        self.current_index = None
        self.playlist_delegate = PlaylistDelegate()

    def _setup_player(self):
        self.video_widget = phonon.Phonon.VideoWidget()
        self.audio_output = phonon.Phonon.AudioOutput()
        self.media_object = phonon.Phonon.MediaObject()
        self.media_object.aboutToFinish.connect(self.queue_next_track)
        self.media_object.currentSourceChanged.connect(self.update_title)
        phonon.Phonon.createPath(self.media_object, self.video_widget)
        phonon.Phonon.createPath(self.media_object, self.audio_output)
        self.player_widget = QtGui.QWidget()
        self.player_layout = QtGui.QHBoxLayout()
        self.player_layout.addWidget(self.video_widget)
        self.player_widget.setLayout(self.player_layout)

    def _setup_playlist(self):
        self.playlist_view = QtGui.QTableView()
        self.playlist_view.setAcceptDrops(True)
        self.playlist_view.setDragEnabled(True)
        self.playlist_view.setDropIndicatorShown(True)
        self.playlist_view.setAlternatingRowColors(True)
#        self.playlist_view.setDragDropMode(QtGui.QAbstractItemView.DropOnly)
        self.playlist_model = PlaylistModel()
        self.playlist_proxy = QtGui.QSortFilterProxyModel()
        self.playlist_proxy.setSourceModel(self.playlist_model)
        self.playlist_view.setModel(self.playlist_proxy)
        self.playlist_view.resizeRowsToContents()
        self.playlist_view.hideColumn(PlaylistModel.FILE)
        self.playlist_view.setAlternatingRowColors(True)
        self.playlist_view.horizontalHeader().resizeSections(
            QtGui.QHeaderView.Stretch)
#        self.playlist_view.setUniformRowHeights(True)
        self.playlist_view.doubleClicked.connect(self.play)

    # TODO - split this up
    def _setup_widgets(self):
        self.dir_view = QtGui.QTreeView()
        self.dir_view.setSelectionMode(
            QtGui.QAbstractItemView.ContiguousSelection)
        media_filter = ["*%s" % extension for extension in
                        self.playlist_model.media_file_extensions]
        self.dir_model = SimpleDirModel(filter_=media_filter)
        self.dir_view.setModel(self.dir_model)
        self.dir_view.setDragEnabled(True)

        self.tab_widget = QtGui.QTabWidget()
        self.tab_widget.setTabPosition(QtGui.QTabWidget.West)

        self.tab_widget.addTab(self.player_widget, "Player Window")

        # TODO: Convert this to a vertical splitter
        self.playlist_widget = QtGui.QWidget()
        self.playlist_layout = QtGui.QVBoxLayout()
        self.playlist_widget.setLayout(self.playlist_layout)
#        self.playlist_layout.addWidget(self.dir_view)
        filter_text = QtGui.QLineEdit()
        filter_text.textEdited.connect(self._filter_playlist)
        self.playlist_layout.addWidget(filter_text)
        self.playlist_layout.addWidget(self.playlist_view)

        self.dir_widget = QtGui.QWidget()
        self.dir_layout = QtGui.QVBoxLayout()
        self.dir_widget.setLayout(self.dir_layout)
        self.dir_layout.addWidget(self.dir_view)
#        self.dir_layout.addWidget(self.playlist_video_widget)
        self.splitter = QtGui.QSplitter(QtCore.Qt.Horizontal)
#        self.splitter.addWidget(self.dir_view)
        self.splitter.addWidget(self.dir_widget)
        # self.splitter.addWidget(self.playlist_view)
        self.splitter.addWidget(self.playlist_widget)

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
            "Play", self.play_pause, "media-playback-start",
            QtCore.Qt.Key_Space)
        stop_action = self._add_action(
            "Stop", self.media_object.stop, "media-playback-stop")
        # TODO - plug up to something
        next_action = self._add_action(
            "Next", self.next, "media-skip-forward")

        # TODO - probably need this to handle state changes
        self.media_object.stateChanged.connect(self.play_pause_icon)

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
        for file_ in files:
            row = self.playlist_model.rowCount()
            self.playlist_model.insertRows(row)
            self.playlist_model.setData(
                self.playlist_model.index(row, PlaylistModel.FILE),
                QtCore.QVariant(file_))
            index = self.playlist_model.index(row, 0)
        self.playlist_view.resizeRowsToContents()

    def play_pause_icon(self, new_state, old_state):
        if new_state in self.NOT_PLAYING_STATES:
            self.play_pause_action.setIcon(kdeui.KIcon("media-playback-start"))
            self.play_pause_action.setText("Play")
        else:
            self.play_pause_action.setIcon(kdeui.KIcon("media-playback-pause"))
            self.play_pause_action.setText("Pause")

    def play_pause(self):
        if self.media_object.state() in self.NOT_PLAYING_STATES:
            self.media_object.play()
        else:
            self.media_object.pause()

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
        file_ = self.playlist_model.data(file_index).toString()
        self.current_index = file_index
        media_source = phonon.Phonon.MediaSource(file_)
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
        self.playlist_model.active_track_row += 1
        file_ = self.playlist_model.data(next_index).toString()
        media_source = phonon.Phonon.MediaSource(file_)
        self.media_object.enqueue(media_source)

    def update_title(self, source):
        file_ = os.path.split(unicode(source.url().toString()))[-1]
        self.setWindowTitle(u"%s - Ersatz" % file_)

    def _filter_playlist(self, filter_re):
        self.playlist_proxy.setFilterRegExp(
            QtCore.QRegExp(
                filter_re, QtCore.Qt.CaseInsensitive,
                QtCore.QRegExp.FixedString))
        self.playlist_proxy.setFilterKeyColumn(1)


def get_about_data():
    app_name = "ersatz"
    catalog = ""
    program_name = kdecore.ki18n("Ersatz")
    version = "0.1"
    description = kdecore.ki18n("A simple Media Player")
    license_ = kdecore.KAboutData.License_GPL
    copyright_ = kdecore.ki18n("(c) 2009 Carlos Corbacho")
    text = kdecore.ki18n("none")
    home_page = "www.strangeworlds.co.uk"
    bug_email = "carlos@strangeworlds.co.uk"
    return kdecore.KAboutData(
        app_name, catalog, program_name, version, description, license_,
        copyright_, text, home_page, bug_email)


def main(argv):
    about_data = get_about_data()
    kdecore.KCmdLineArgs.init(argv, about_data)
    app = kdeui.KApplication()
    player = MediaPlayer()
    player.show()
    app.exec_()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
