import sys
from unittest.mock import MagicMock

def mock_if_missing(module_names):
    for name in module_names:
        try:
            __import__(name)
        except ImportError:
            sys.modules[name] = MagicMock()

# Only mock modules that are truly problematic or missing in the test environment
# to allow real unit testing of installed packages.
problematic_modules = [
    'langgraph',
    'langgraph.graph',
    'edgartools', # Can be heavy/network dependent
    'langfuse',
    'langfuse.decorators',
    'sec_edgar_downloader',
    'langchain_text_splitters',
    'bs4',
]

mock_if_missing(problematic_modules)

# We don't globally mock api.config.Config here as it breaks Config tests.
# If a specific test needs it mocked, it should do so itself.
