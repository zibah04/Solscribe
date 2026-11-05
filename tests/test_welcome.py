"""First-run consent, replay, sample practice, and compact footer regressions."""
import pytest
from PySide6.QtWidgets import QWizard
from test_live_ui import app, window


def test_guide_appears_once_and_can_be_reopened(window, app):
    window.start_first_run()
    guide = window._guide
    assert guide is not None and len(guide.pageIds()) == 4
    guide.reject()
    assert window._guide is None and window.settings.value('welcome_seen', type=bool)
    window.start_first_run()
    assert window._guide is None
    window.show_quick_guide()
    assert window._guide is not None
    window._guide.reject()


def test_guide_applies_choices_and_practice_preserves_existing_work(window, app):
    window.load_demo()
    original = window.session_id
    window.doc_edits['Summary'].setPlainText('Original meeting notes')
    window.show_quick_guide()
    guide = window._guide
    guide.appearance.setCurrentIndex(guide.appearance.findData('light'))
    guide.live_words.setChecked(False)
    guide.practice.setChecked(True)
    for _ in range(3): guide.next()
    app.processEvents()
    assert guide.currentId() == 3 and guide.button(QWizard.FinishButton).isVisible()
    guide.accept()
    assert window.settings.value('welcome_completed', type=bool)
    assert not window.live_checkbox.isChecked() and window.theme_name == 'light'
    assert window.session_id != original
    assert window.store.get(original)['summary'] == 'Original meeting notes'
    assert not window.auto_updates_checkbox.isChecked()


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('size', [(1092, 570), (683, 340)])
def test_footer_and_guide_remain_accessible_on_small_windows(window, app, theme, size):
    window.resize(*size); window.set_theme(theme)
    app.processEvents()
    assert window.credit_label.text() == 'zibah@2026'
    for control in (window.credit_label, window.guide_btn, window.updates_btn):
        assert control.isVisible()
        assert window.rect().contains(control.mapTo(window, control.rect().center()))
    window.show_quick_guide()
    assert window._guide is not None
    window._guide.reject()
