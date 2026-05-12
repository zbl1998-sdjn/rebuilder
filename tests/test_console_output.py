from core.meta_controller import progress_columns
from main import banner_text


def test_banner_text_is_ascii_safe_for_windows_console():
    banner_text().encode("ascii")


def test_progress_columns_do_not_use_unicode_spinner():
    columns = progress_columns("Testing...")

    assert all(column.__class__.__name__ != "SpinnerColumn" for column in columns)
