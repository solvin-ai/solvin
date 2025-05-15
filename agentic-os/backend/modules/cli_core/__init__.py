# modules/cli_core/__init__.py

# Apply all patches immediately (monkey-patch click/typer internals)
from .patch import *

# Re-export banner utilities and HTTP timeout
from .utils import banner, set_no_banner, set_http_timeout

# Re-export our custom Typer group and the global callback
from .core import BannerGroup, global_callback
