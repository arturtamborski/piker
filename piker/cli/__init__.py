"""
CLI commons.
"""
import os

import click
import tractor

from ..log import get_console_log, get_logger
from ..brokers import get_brokermod, config

log = get_logger('cli')
DEFAULT_BROKER = 'questrade'

_config_dir = click.get_app_dir('piker')
_watchlists_data_path = os.path.join(_config_dir, 'watchlists.json')
_context_defaults = dict(
    default_map={
        # Questrade specific quote poll rates
        'monitor': {
            'rate': 3,
        },
        'optschain': {
            'rate': 1,
        },
    }
)


@click.command()
@click.option('--loglevel', '-l', default='warning', help='Logging level')
@click.option('--tl', is_flag=True, help='Enable tractor logging')
@click.option('--host', '-h', default='127.0.0.1', help='Host address to bind')
def pikerd(loglevel, host, tl):
    """Spawn the piker broker-daemon.
    """
    from ..data import _data_mods
    get_console_log(loglevel)
    tractor.run_daemon(
        rpc_module_paths=_data_mods,
        name='brokerd',
        loglevel=loglevel if tl else None,
    )


@click.group(context_settings=_context_defaults)
@click.option('--broker', '-b', default=DEFAULT_BROKER,
              help='Broker backend to use')
@click.option('--loglevel', '-l', default='warning', help='Logging level')
@click.option('--configdir', '-c', help='Configuration directory')
@click.pass_context
def cli(ctx, broker, loglevel, configdir):
    if configdir is not None:
        assert os.path.isdir(configdir), f"`{configdir}` is not a valid path"
        config._override_config_dir(configdir)

    ctx.ensure_object(dict)
    ctx.obj.update({
        'broker': broker,
        'brokermod': get_brokermod(broker),
        'loglevel': loglevel,
        'log': get_console_log(loglevel),
        'confdir': _config_dir,
        'wl_path': _watchlists_data_path,
    })


def _load_clis() -> None:
    from ..data import marketstore as _
    from ..brokers import cli as _  # noqa
    from ..ui import cli as _  # noqa
    from ..watchlists import cli as _  # noqa


# load downstream cli modules
_load_clis()
