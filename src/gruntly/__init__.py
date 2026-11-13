from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("gruntly")
except PackageNotFoundError:        # run from a source tree that was never installed
    __version__ = "0+unknown"
