import logging

from app.core.logging_config import setup_logging


def test_setup_logging_sets_root_level():
    setup_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG

    setup_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_setup_logging_unknown_level_defaults_to_info():
    setup_logging("NOT_A_LEVEL")
    assert logging.getLogger().level == logging.INFO
