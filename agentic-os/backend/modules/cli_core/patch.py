# modules/cli_core/patch.py

import click
from click.core import Context as _ClickContext, Parameter as _ClickParameter
from click.core import Command as _ClickCommand, Group as _ClickGroup
from click.formatting import HelpFormatter

# ——————————————————————————————————————————————————————
# 1) For Click <8.0.0: strip unsupported kwargs from Context.__init__
#    so that context_settings={'no_args_is_help':True} etc. don't blow up.
# ——————————————————————————————————————————————————————
try:
    vers = tuple(int(x) for x in click.__version__.split('.')[:3])
except Exception:
    vers = (0, 0, 0)

if vers < (8, 0, 0):
    _orig_ctx_init = _ClickContext.__init__

    def _patched_ctx_init(self, *args, **kwargs):
        kwargs.pop("invoke_without_command", None)
        kwargs.pop("no_args_is_help",      None)
        return _orig_ctx_init(self, *args, **kwargs)

    _ClickContext.__init__ = _patched_ctx_init

    # NOTE: we *do not* override make_formatter here.  Old‐Click help still works.

# ——————————————————————————————————————————————————————
# 2) Fix Typer/Click mismatch: allow Parameter.make_metavar(ctx=None)
# ——————————————————————————————————————————————————————
_orig_make_metavar = _ClickParameter.make_metavar

def _patched_make_metavar(self, ctx=None):
    return _orig_make_metavar(self, ctx)

_ClickParameter.make_metavar = _patched_make_metavar
