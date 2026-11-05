"""Shared colors for the desktop, editors and dialogs."""
from string import Template
from pathlib import Path
import sys
from PySide6.QtGui import QColor, QPalette

THEMES = {
    'dark': dict(bg='#0B1120', side='#111A2D', panel='#141E32', field='#0C1526',
                 ink='#E7EAF4', muted='#A3AEC6', border='#33425E', accent='#6E60DF',
                 accent_hover='#7363DE', accent_ink='#C7C0FF', tint='#292E55',
                 hover='#25324A', alternate='#172238', header='#1D2A42',
                 disabled='#1B2436', disabled_ink='#8793AD', record='#3B2539',
                 record_ink='#FFB5CC', record_border='#975975', scroll='#46546D'),
    'light': dict(bg='#F5F5FC', side='#ECEEF8', panel='#FFFFFF', field='#FFFFFF',
                  ink='#22273B', muted='#59647B', border='#CDD2E3', accent='#6554D6',
                  accent_hover='#5946C7', accent_ink='#5846C5', tint='#EAE6FF',
                  hover='#E2E5F3', alternate='#F4F5FC', header='#ECEEF8',
                  disabled='#E9EBF3', disabled_ink='#717A91', record='#FCEBF2',
                  record_ink='#982D56', record_border='#D09AB0', scroll='#B6BDD2'),
}

_STYLE = Template(r'''
QWidget { background: $bg; color: $ink; font-family: "Segoe UI"; font-size: 10pt; }
QLabel, QCheckBox { background: transparent; }
QMainWindow, QWidget#AppRoot { background: $bg; }
QFrame#Sidebar { background: $side; border-right: 1px solid $border; }
QLabel#LogoIcon { color: white; background: #7567E8; border-radius: 13px; font-size: 21pt; font-weight: bold; }
QLabel#Brand { color: $ink; font-size: 19pt; font-weight: 700; }
QLabel#BrandTag, QLabel#Hint, QLabel#Muted { color: $muted; font-size: 9pt; }
QLabel#Eyebrow { color: $muted; font-size: 9pt; font-weight: 700; letter-spacing: 1px; }
QLabel#Headline { color: $ink; font-size: 18pt; font-weight: 700; }
QLabel#SettingLabel { color: $muted; font-size: 9pt; }
QFrame#Panel, QFrame#SettingPanel { background: $panel; border: 1px solid $border; border-radius: 12px; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox { background: $field; color: $ink; border: 1px solid $border; border-radius: 8px; padding: 7px; selection-background-color: $accent; selection-color: white; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid $accent; }
QLineEdit#TitleInput { background: transparent; border: none; padding: 0px; font-size: 19pt; font-weight: 700; color: $ink; }
QComboBox { padding: 7px 10px; }
QComboBox QAbstractItemView { background: $field; color: $ink; border: 1px solid $accent; selection-background-color: $accent; selection-color: white; }
QPushButton, QToolButton { background: $hover; border: 1px solid $border; border-radius: 8px; padding: 8px 12px; color: $ink; font-weight: 600; }
QPushButton:hover, QToolButton:hover { background: $tint; border-color: $accent; }
QPushButton:focus, QToolButton:focus { border: 1px solid $accent; }
QPushButton:pressed, QToolButton:pressed { background: $tint; }
QPushButton:disabled, QToolButton:disabled { background: $disabled; color: $disabled_ink; border-color: $border; }
QPushButton#Primary { background: $accent; border-color: $accent; color: white; }
QPushButton#Primary:hover { background: $accent_hover; }
QPushButton#Primary:disabled { background: $disabled; color: $disabled_ink; border-color: $border; }
QPushButton#Record { background: $record; border-color: $record_border; color: $record_ink; }
QPushButton#Record:hover { background: $record; border-color: $record_ink; }
QPushButton#Recording { background: #AE3157; color: white; border-color: #AE3157; }
QPushButton#Plain { background: transparent; color: $ink; }
QPushButton#Plain:hover { background: $hover; }
QCheckBox { color: $ink; spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid $muted; border-radius: 3px; background: $field; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url("$check_icon"); }
QCheckBox::indicator:disabled { border-color: $border; background: $disabled; }
QListWidget { background: transparent; border: none; outline: none; padding: 2px; }
QListWidget::item { color: $ink; border-radius: 8px; padding: 10px; margin: 2px 0; }
QListWidget::item:hover { background: $hover; }
QListWidget::item:selected { background: $tint; color: $accent_ink; border: 1px solid $accent; }
QTabWidget::pane { border: 1px solid $border; border-radius: 10px; background: $panel; }
QTabBar::tab { background: transparent; color: $muted; padding: 9px 12px; font-weight: 600; border-bottom: 2px solid transparent; }
QTabBar::tab:hover { color: $ink; }
QTabBar::tab:selected { color: $accent_ink; border-bottom: 2px solid $accent; }
QTableWidget { background: $field; alternate-background-color: $alternate; border: none; gridline-color: $border; selection-background-color: $tint; selection-color: $ink; }
QTableWidget::item { padding: 8px; }
QHeaderView::section { background: $header; color: $muted; padding: 10px; border: none; border-bottom: 1px solid $border; font-weight: 600; }
QScrollArea { border: none; background: $bg; }
QScrollBar:vertical { background: $bg; width: 11px; margin: 1px; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 5px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar:horizontal { background: $bg; height: 10px; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 5px; }
QProgressBar { background: $border; border: none; border-radius: 3px; height: 6px; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
QSlider::groove:horizontal { height: 5px; background: $border; border-radius: 2px; }
QSlider::handle:horizontal { background: $accent; width: 12px; margin: -4px 0; border-radius: 6px; }
QMenu { background: $panel; border: 1px solid $border; padding: 6px; color: $ink; }
QMenu::item { padding: 8px 23px; border-radius: 5px; }
QMenu::item:selected { background: $tint; color: $ink; }
QStatusBar { color: $muted; background: $bg; border-top: 1px solid $border; }
QMessageBox, QInputDialog, QFileDialog { background: $panel; }
QToolTip { color: $ink; background: $panel; border: 1px solid $border; padding: 6px; }
''')


def stylesheet(name):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return _STYLE.substitute(THEMES.get(name, THEMES['dark']), check_icon=(root / 'assets' / 'check.png').as_posix())


def palette(name):
    colors = THEMES.get(name, THEMES['dark'])
    result = QPalette()
    roles = {'Window': 'bg', 'WindowText': 'ink', 'Base': 'field', 'AlternateBase': 'alternate',
             'Text': 'ink', 'Button': 'hover', 'ButtonText': 'ink', 'Highlight': 'accent',
             'Link': 'accent_ink', 'ToolTipBase': 'panel', 'ToolTipText': 'ink', 'PlaceholderText': 'muted'}
    for role, color in roles.items():
        result.setColor(getattr(QPalette.ColorRole, role), QColor(colors[color]))
    result.setColor(QPalette.HighlightedText, QColor('white'))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        result.setColor(QPalette.Disabled, role, QColor(colors['disabled_ink']))
    return result
