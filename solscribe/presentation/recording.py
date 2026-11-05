"""Recording presentation controller; device I/O and finalization run in workers."""
from datetime import datetime
import queue
import uuid
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QTableWidgetItem
from ..recorder import MicrophoneRecorder, SystemLoopbackRecorder
from ..combined import CombinedRecorder
from ..live import LiveTranscriptionWorker
from ..jobs import OperationWorker
from ..reports import stamp


class RecordingActions:
    def _live_option_changed(self, enabled):
        self.settings.setValue('live_captions', enabled)
        if not self.record_timer.isActive():
            self.record_btn.setText(self.record_label())

    def toggle_record(self):
        if self.record_timer.isActive():
            self.persist()
            self.record_timer.stop()
            self.record_btn.setText('Finishing…')
            self.status_label.setText('Saving recording and finishing the last words…')
            self._stopping_active = True
            self._stop_worker = OperationWorker(self.recorder.stop, self)
            self._stop_worker.done.connect(self._recording_stopped)
            self._stop_worker.failed.connect(self._recording_stop_failed)
            self._stop_worker.finished.connect(self._recording_stop_finished)
            self._stop_worker.start()
            self.update_actions()
            return
        if self._is_busy():
            QMessageBox.information(self, 'Busy', 'Complete the current task before recording.')
            return
        if not self.session_id and not self.new_session():
            return
        # A new audio capture must never silently mismatch an old transcript.
        if self.current_session and (self.current_session.get('audio_path') or self.current_session.get('segments')):
            if not self.new_session():
                return
            self.title_edit.setText('Meeting · ' + datetime.now().strftime('%d %b %Y %H:%M'))
            self.persist()
        if not self.persist():
            return
        path = self.store.recordings / f'{uuid.uuid4().hex}.wav'
        live_enabled = self.live_checkbox.isChecked()
        self._live_failed_message = None
        try:
            selected_device = self.mic_combo.currentData()
            mode = self.capture_mode.currentData()
            if mode == 'combined':
                if isinstance(selected_device, str):
                    raise ValueError('Choose a microphone rather than a PC audio device for combined recording')
                self.recorder = CombinedRecorder()
                device = {'microphone': selected_device, 'system': self.system_combo.currentData()}
            elif mode == 'system':
                self.recorder = SystemLoopbackRecorder()
                device = self.system_combo.currentData()
            elif isinstance(selected_device, str) and selected_device.startswith('loopback:'):
                self.recorder = SystemLoopbackRecorder()
                device = selected_device[len('loopback:'):]
            else:
                self.recorder = MicrophoneRecorder()
                device = selected_device
            live_queue = queue.Queue(maxsize=32) if live_enabled else None
            self.recorder.live_queue = live_queue
            self.recorder.start(path, device)
            self.store.update(self.session_id, audio_path=str(path), duration=0,
                              model='live' if live_enabled else '', audio_owned=True, recording_state='active', recording_pid=os.getpid(),
                              source_tracks=getattr(self.recorder, 'source_tracks', None))
            self.current_session = self.store.get(self.session_id)
            self.audio_name.setText('Recording this meeting…')
            self.playback_controls.hide()
            if live_enabled:
                model = self.live_model_combo.currentData()
                self._live_session_id = self.session_id
                self._live_failed_message = None
                self.caption_status.setText('Getting ready to listen · first use needs a download. Your recording is safe.')
                self.search_transcript.clear()
                self._live_active = True
                self._live_worker = LiveTranscriptionWorker(
                    live_queue, model, self.language_combo.currentData(), self.store.models, self)
                self._live_worker.status.connect(self._live_status)
                self._live_worker.segment_batch.connect(self._live_segments)
                self._live_worker.failed.connect(self._live_failed)
                self._live_worker.finished.connect(self._live_finished)
                self._live_worker.start()
                self.focus_tab(0)
            else:
                self.caption_status.setText('Recording only · enable live transcription before your next recording for captions')
            self.record_btn.setText('Stop recording')
            self.record_btn.setObjectName('Recording')
            self.record_btn.style().unpolish(self.record_btn)
            self.record_btn.style().polish(self.record_btn)
            self.status_label.setText('Recording · getting ready to show your words…' if live_enabled
                                      else 'Recording…')
            self.record_timer.start()
            self.update_actions()
        except Exception as exc:
            if not self._live_worker or not self._live_worker.isRunning():
                self._live_active = False
            if self.recorder.active:
                self.recorder.stop()
            self._show_error('Microphone unavailable',
                'We could not start recording. Choose another microphone below, or allow microphone access in Windows Settings.', exc)

    def _refresh_recording(self):
        duration = stamp(self.recorder.elapsed)
        bars = int(min(1, self.recorder.level * 7) * 12)
        caption = ' · LIVE' if self._live_worker and self._live_worker.isRunning() else ''
        if self._live_worker and self._live_worker.isRunning():
            behind = max(0, int(self.recorder.elapsed - self._live_worker.processed_seconds))
            caption += f' · ~{behind}s pending' if behind >= 10 else ''
        if self.recorder.live_dropped:
            caption += ' · Some live words skipped; improve transcript after recording'
        if self._live_failed_message:
            caption = ' · WORDS UNAVAILABLE · recording continues'
        elif self.recorder.elapsed >= 3 and self.recorder.level < 0.0001:
            caption += ' · No sound detected · check your microphone'
        self.status_label.setText(f'● Recording {duration}{caption}    {"▮" * bars}{"▯" * (12 - bars)}')
        if not self.recorder.active:
            # An audio backend may fail asynchronously (e.g., unplugged loopback).
            self.toggle_record()

    def _live_status(self, message):
        self.caption_status.setText(message)
        if not self.record_timer.isActive():
            self.status_label.setText(message)
        self.statusBar().showMessage(message, 6000)

    def _live_segments(self, new_segments):
        if self._live_session_id != self.session_id or not new_segments:
            return
        # No reload while recording, so the user's current focus and edits survive.
        manual_pending = self.save_timer.isActive() or bool(self._save_error)
        self.table.blockSignals(True)
        for part in new_segments:
            row = self.table.rowCount()
            self.table.insertRow(row)
            time_cell = QTableWidgetItem(stamp(part.get('start', 0)))
            time_cell.setFlags(time_cell.flags() & ~Qt.ItemIsEditable)
            time_cell.setData(Qt.UserRole, float(part.get('start', 0)))
            time_cell.setData(Qt.UserRole + 1, float(part.get('end', 0)))
            self.table.setItem(row, 0, time_cell)
            self.table.setItem(row, 1, QTableWidgetItem(part.get('speaker') or 'Speaker'))
            self.table.setItem(row, 2, QTableWidgetItem(part.get('text') or ''))
        self.table.blockSignals(False)
        self.transcript_stack.setCurrentIndex(0)
        for row in range(self.table.rowCount() - len(new_segments), self.table.rowCount()):
            self.table.setRowHidden(row, False)
        self.table.scrollToBottom()
        self.resize_visible_rows()
        if manual_pending:
            self.persist()
        else:
            # Avoid scanning thousands of Qt cells for every live batch. The
            # cached transcript is authoritative when no manual edit is pending.
            updated = self.current_session.get('segments', []) + new_segments
            try:
                self.store.update(self.session_id, segments=updated)
            except Exception as exc:
                self._save_error = str(exc)
            self.current_session['segments'] = updated
            self.update_actions()

    def _live_failed(self, message):
        self._live_failed_message = message
        self.caption_status.setText('Words cannot be shown right now. Your recording is safe; create a transcript when you finish.')
        self.status_label.setText('Recording continues · words are temporarily unavailable')

    def _live_finished(self):
        self._live_active = False
        if not self.record_timer.isActive():
            self.persist()
            count = self.table.rowCount()
            message = ('Your recording is safe. Click Create transcript to recover the words.' if self._live_failed_message
                       else '✓ Your words are saved. Choose Improve transcript for a more accurate version.' if count
                       else 'No words recognized. Check your microphone and language, or try Create transcript.')
            self.status_label.setText(message)
            self.caption_status.setText(message)
        self.update_actions()

    def _recording_stopped(self, path):
        try:
            self.store.update(self.session_id, audio_path=str(path), duration=self.recorder.elapsed,
                              recording_state='complete', recording_pid=0, audio_owned=True,
                              source_tracks=getattr(self.recorder, 'source_tracks', None))
            self.load_session(self.session_id)
            if self.recorder.error:
                self._show_error('Check your recording',
                                 'Some sound may be missing. Available recordings and separate source tracks have been kept.',
                                 self.recorder.error)
            if self.recorder.live_dropped:
                self.caption_status.setText('Some live words were skipped. Use Improve transcript to read the saved recording.')
        except Exception as exc:
            self._save_error = str(exc)
            self.status_label.setText('Recording is on disk, but meeting details could not be saved. Check available space.')
        if self._live_worker and self._live_worker.isRunning():
            self._live_worker.stop()
            self.caption_status.setText('Recording saved · finishing queued live words…')

    def _recording_stop_failed(self, details):
        self._show_error('Recording did not finish normally',
                         'Please check the saved audio and selected devices. Do not discard the source recordings.', details)
        if self._live_worker:
            self._live_worker.stop()

    def _recording_stop_finished(self):
        self._stopping_active = False
        if self.recorder.active:
            self.record_timer.start()
            self.record_btn.setText('Stop recording')
        else:
            self.record_btn.setText(self.record_label())
            self.record_btn.setObjectName('Record')
            self.record_btn.style().unpolish(self.record_btn)
            self.record_btn.style().polish(self.record_btn)
        self.update_actions()

