"""Global test safety net.

Importing the bot calls load_dotenv() (bot/utils/config.py, bot/utils/handler_registry.py),
which pulls the REAL Google Sheet id and service-account path into the environment. Without
this fixture, any test that builds a real handler and forgets to stub the sheet layer writes
rows into PRODUCTION finance data -- which has happened. Blank the credentials for the whole
test session so the sheet layer always short-circuits, and no test can reach the network.
"""
import os
import pytest

_SHEET_ENV = ("GOOGLE_SHEET_ID", "GOOGLE_CREDENTIALS_FILE", "JSON_FILE_PATH",
              "TRON_API_KEY", "ETHEREUM_API_KEY")


@pytest.fixture(autouse=True, scope="session")
def _never_touch_production():
    saved = {k: os.environ.get(k) for k in _SHEET_ENV}
    for k in _SHEET_ENV:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
