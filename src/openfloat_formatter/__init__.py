"""OpenFloat Data Formatter — Process Maker exports → OpenFloat uploads."""

from importlib.metadata import PackageNotFoundError, version

__version__ = "0.1.0"


def app_version() -> str:
    """The installed version, shown in the app's sidebar."""
    try:
        return version("openfloat-data-formatter")
    except PackageNotFoundError:  # running from a checkout that isn't installed
        return "dev"
