"""A short, optional setup wizard with real preferences and a sample practice path."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QLabel, QComboBox, QCheckBox,
    QWidget, QScrollArea,
)


class QuickGuide(QWizard):
    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle('Welcome to SolScribe')
        self.setWizardStyle(QWizard.ClassicStyle)
        self.setButtonText(QWizard.CancelButton, 'Skip for now')
        self.setButtonText(QWizard.FinishButton, 'Start using SolScribe')
        self.setOption(QWizard.NoBackButtonOnStartPage)

        first = self.page_layout('1 of 4 · Make it yours',
            'Capture a conversation, review the words, then turn them into useful notes. '
            'Your recordings stay on this PC. You can reopen this guide from the footer or Settings.')
        first.addWidget(QLabel('Choose an appearance'))
        self.appearance = QComboBox()
        self.appearance.addItem('Dark', 'dark')
        self.appearance.addItem('Light', 'light')
        self.appearance.setCurrentIndex(self.appearance.findData(window.theme_name))
        self.appearance.setAccessibleName('Guide appearance')
        self.appearance.currentIndexChanged.connect(lambda: window.set_theme(self.appearance.currentData()))
        first.addWidget(self.appearance)
        first.addWidget(QLabel('What would you like to capture?'))
        self.purpose = self.copy_combo(window.mode_combo, 'Guide recording purpose')
        first.addWidget(self.purpose)
        self.add_text(first, 'Meeting creates summaries and minutes. Lecture creates study notes and revision cards. You can switch later; both sets of notes are kept.')
        first.addStretch(1)

        audio = self.page_layout('2 of 4 · Choose your sound',
            'Use Microphone for your voice, Computer audio for sound played by this PC, or Both sources for an online meeting. '
            'Headphones help keep playback out of the microphone. Windows must allow microphone access for desktop apps.')
        audio.addWidget(QLabel('Recording source'))
        self.source = self.copy_combo(window.capture_mode, 'Guide recording source')
        audio.addWidget(self.source)
        audio.addWidget(QLabel('Microphone'))
        self.microphone = self.copy_combo(window.mic_combo, 'Guide microphone')
        audio.addWidget(self.microphone)
        self.add_text(audio, 'You can change these inputs at the bottom of the app. The computer playback device is in Settings.')
        audio.addStretch(1)

        record = self.page_layout('3 of 4 · Record and review',
            'Click Record meeting or Record lecture and watch the sound meter. On first use, a speech model downloads before Listening appears. '
            'Words arrive in short batches as you speak. Click Stop recording when finished and wait for the last words.')
        self.live_words = QCheckBox('Show words while I speak')
        self.live_words.setChecked(window.live_checkbox.isChecked())
        record.addWidget(self.live_words)
        self.add_text(record, 'Double-click words or speaker names to correct them. Improve transcript rereads the saved recording '
                      'and lets you compare the result before replacing your edits. You can also add a recording or paste text.')
        record.addStretch(1)

        notes = self.page_layout('4 of 4 · Create, save and stay current',
            'Click Create notes for a summary, minutes and action items. Review names, decisions and dates, then use Save a copy '
            'for Word or PDF. In Lecture, choose Create study notes, then practise with Revision: try answering, reveal the answer, '
            'and check Sources. Verify technical terms and formulas. Changes save automatically. Settings also has backup and restore.')
        self.practice = QCheckBox('Open a sample so I can practise')
        self.practice.setChecked(False)
        notes.addWidget(self.practice)
        self.add_text(notes, 'The sample contains saved text; it does not listen to your microphone.')
        self.updates = QCheckBox('Tell me about updates when SolScribe opens')
        self.updates.setChecked(window.auto_updates_checkbox.isChecked())
        notes.addWidget(self.updates)
        self.add_text(notes, 'Update checks contact GitHub for version information. Recordings and notes are not sent. '
                      'You choose when to download and install. You can also check manually from Updates in the footer.')
        notes.addStretch(1)
        for role in (QWizard.NextButton, QWizard.FinishButton):
            self.button(role).setObjectName('Primary')
        geometry = self.screen().availableGeometry()
        self.resize(min(640, geometry.width() - 30), min(470, geometry.height() - 40))

    @staticmethod
    def copy_combo(original, name):
        combo = QComboBox()
        for index in range(original.count()):
            combo.addItem(original.itemText(index), original.itemData(index))
        combo.setCurrentIndex(original.currentIndex())
        combo.setAccessibleName(name)
        return combo

    @staticmethod
    def add_text(layout, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.PlainText)
        layout.addWidget(label)

    def page_layout(self, title, text):
        page = QWizardPage()
        page.setTitle(title)
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(12)
        self.add_text(layout, text)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.addPage(page)
        return layout
