"""Smoke tests for the Streamlit app: both pages render without an exception.

AppTest can't drive a file upload, so this covers the empty state only — the
pipeline behind each page has its own tests.
"""

import signal
import threading

from streamlit.testing.v1 import AppTest

import openfloat_formatter.ui.app as app_module

APP = app_module.__file__


def test_prepare_upload_page_renders():
    at = AppTest.from_file(APP).run()
    assert not at.exception
    assert any("Upload a file to get started" in info.value for info in at.info)


def test_payment_results_page_renders():
    at = AppTest.from_file(APP).run()
    at.radio[0].set_value(at.radio[0].options[1]).run()
    assert not at.exception
    assert any("Transaction Statement" in info.value for info in at.info)


def test_bad_country_prefix_stops_the_page():
    at = AppTest.from_file(APP).run()
    at.text_input[0].set_value("+254").run()
    assert not at.exception
    assert any("1 to 3 digits" in error.value for error in at.error)


def test_close_button_is_in_the_sidebar():
    at = AppTest.from_file(APP).run()
    assert any(button.label == "Close the app" for button in at.sidebar.button)


def test_closing_shows_goodbye_and_stops_the_server(monkeypatch):
    # The real signal would stop pytest itself; record it instead.
    raised = threading.Event()
    monkeypatch.setattr(signal, "raise_signal", lambda signum: raised.set())

    at = AppTest.from_file(APP)
    at.session_state["closing"] = True
    at.run()

    assert not at.exception
    assert any("The app has closed" in s.value for s in at.success)
    assert not at.radio  # the page itself is not drawn once closing
    assert raised.wait(timeout=5)
