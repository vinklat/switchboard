# -*- coding: utf-8 -*-
'''cmd line argument parser for the Switchboard http server'''

import logging
from argparse import ArgumentParser, ArgumentTypeError
from switchboard.version import __version__, get_build_info

_LOG_LEVEL_STRINGS = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']


def log_level_string_to_int(log_level_string):
    '''get log level int from string'''

    if log_level_string not in _LOG_LEVEL_STRINGS:
        message = 'invalid choice: {0} (choose from {1})'.format(
            log_level_string, _LOG_LEVEL_STRINGS)
        raise ArgumentTypeError(message)

    log_level_int = getattr(logging, log_level_string, logging.INFO)
    # check the log_level_choices have not changed from our expected values
    assert isinstance(log_level_int, int)

    return log_level_int


def get_pars():
    '''get parameters from from command line arguments'''

    parser = ArgumentParser(description='Switchboard {}'.format(__version__))
    parser.add_argument('-a',
                        '--address',
                        action='store',
                        dest='addr',
                        help='listen address',
                        type=str,
                        default="")
    parser.add_argument('-p',
                        '--port',
                        action='store',
                        dest='port',
                        help='listen port',
                        type=int,
                        default=9128)
    parser.add_argument('-c',
                        '--sensor-config',
                        action='store',
                        dest='sensors_fname',
                        help='sensor config yaml file',
                        type=str,
                        default='conf/sensors.yml')
    parser.add_argument('-j',
                        '--jinja2',
                        action='store_true',
                        dest='jinja2',
                        help='use jinja2 in sensor config yaml file')
    parser.add_argument('-t',
                        '--time-locale',
                        action='store',
                        dest='time_locale',
                        help='time formatting locale (en-US, cs-CZ , ...)',
                        type=str,
                        default="en-US")

    parser.add_argument('-V',
                        '--version',
                        action='version',
                        version=str(get_build_info()))

    parser.add_argument(
        '-l',
        '--log-level',
        action='store',
        dest='log_level',
        help='set the logging output level. {0}'.format(_LOG_LEVEL_STRINGS),
        type=log_level_string_to_int,
        default='INFO')

    return parser.parse_args()
