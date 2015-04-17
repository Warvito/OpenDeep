"""
.. module:: plot

This module sets up plotting for values during training/testing.

Adapted from Blocks: https://github.com/bartvm/blocks/blob/master/blocks/extensions/plot.py
"""

__authors__ = "Markus Beissinger"
__copyright__ = "Copyright 2015, Vitruvian Science"
__credits__ = ["Markus Beissinger", "Blocks"]
__license__ = "Apache"
__maintainer__ = "OpenDeep"
__email__ = "opendeep-dev@googlegroups.com"

# standard libraries
import logging
import signal
import time
import collections
from subprocess import Popen, PIPE
import warnings
# third party libraries
try:
    from bokeh.plotting import (curdoc, cursession, figure, output_server, push, show)
    from bokeh.models.renderers import GlyphRenderer
    BOKEH_AVAILABLE = True
except ImportError:
    BOKEH_AVAILABLE = False
    warnings.warn("Bokeh is not available - plotting is disabled. Please pip install bokeh.")

from opendeep.utils.misc import make_time_units_string

log = logging.getLogger(__name__)


class Plot(object):
    """
    Live plotting of monitoring channels.

    .. warning::

      Depending on the number of plots, this can add 0.1 to 2 seconds per epoch
      to your training!

    In most cases it is preferable to start the Bokeh plotting server
    manually, so that your plots are stored permanently.

    To start the server manually, type ``bokeh-server`` in the command line.
    This will default to http://localhost:5006.
    If you want to make sure that you can access your plots
    across a network (or the internet), you can listen on all IP addresses
    using ``bokeh-server --ip 0.0.0.0``.

    Alternatively, you can set the ``start_server_flag`` argument to ``True``,
    to automatically start a server when training starts.
    However, in that case your plots will be deleted when you shut
    down the plotting server!

    .. warning::

       When starting the server automatically using the ``start_server_flag``
       argument, the extension won't attempt to shut down the server at the
       end of training (to make sure that you do not lose your plots the
       moment training completes). You have to shut it down manually (the
       PID will be shown in the logs). If you don't do this, this extension
       will crash when you try and train another model with
       ``start_server_flag`` set to ``True``, because it can't run two servers
       at the same time.

    Parameters
    ----------
    bokeh_doc_name : str
        The name of the Bokeh document. Use a different name for each
        experiment if you are storing your plots.
    channels : list of lists of strings
        The names of the monitor channels that you want to plot. The
        channels in a single sublist will be plotted together in a single
        figure, so use e.g. ``[['test_cost', 'train_cost'],
        ['weight_norms']]`` to plot a single figure with the training and
        test cost, and a second figure for the weight norms.
    open_browser : bool, optional
        Whether to try and open the plotting server in a browser window.
        Defaults to ``True``. Should probably be set to ``False`` when
        running experiments non-locally (e.g. on a cluster or through SSH).
    start_server_flag : bool, optional
        Whether to try and start the Bokeh plotting server. Defaults to
        ``False``. The server started is not persistent i.e. after shutting
        it down you will lose your plots. If you want to store your plots,
        start the server manually using the ``bokeh-server`` command. Also
        see the warning above.
    server_url : str, optional
        Url of the bokeh-server. Ex: when starting the bokeh-server with
        ``bokeh-server --ip 0.0.0.0`` at ``alice``, server_url should be
        ``http://alice:5006``. When not specified the default configured
        to ``http://localhost:5006/``.

    """
    # Tableau 10 colors
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
              '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

    defaults = {
        'colors': colors
    }

    def __init__(self, bokeh_doc_name, monitors, open_browser=False,
                 start_server=False, server_url='http://localhost:5006/',
                 colors=None, defaults=defaults, **kwargs):
        # Make sure Bokeh is available
        if BOKEH_AVAILABLE:
            if not isinstance(monitors, collections.Mapping):
                log.error("Monitors needs to be a dictionary")
                raise AssertionError("Monitors needs to be a dictionary")

            self.plots = {}
            self.colors = colors or defaults['colors']
            self.bokeh_doc_name = bokeh_doc_name
            self.server_url = server_url
            self.start_server(start_server_flag=start_server)
            self.monitors = monitors

            # Create figures for each group of monitors
            self.figures = []
            self.figure_indices = {}
            for i, (monitor_group_name, monitor_group_val) in enumerate(self.monitors.items()):
                self.figures.append(figure(title='{} #{}'.format(bokeh_doc_name, monitor_group_name),
                                           logo=None,
                                           toolbar_location='right'))
                if not isinstance(monitor_group_val, collections.Mapping):
                    self.figure_indices[monitor_group_name] = i
                else:
                    for monitor_name in monitor_group_val.keys():
                        monitor_name = '_'.join([monitor_group_name, monitor_name])
                        self.figure_indices[monitor_name] = i

            print self.figure_indices

            if open_browser:
                show(self.figures)

    def update_plots(self, epoch, monitors_dict):
        if BOKEH_AVAILABLE:
            color_idx = 0
            for key, value in monitors_dict.items():
                if key in self.figure_indices:
                    if key not in self.plots:
                        fig = self.figures[self.figure_indices[key]]
                        fig.line([epoch], [value], legend=key,
                                 x_axis_label='iterations',
                                 y_axis_label='value', name=key,
                                 line_color=self.colors[color_idx % len(self.colors)])
                        color_idx += 1
                        renderer = fig.select(dict(name=key, type=GlyphRenderer))
                        self.plots[key] = renderer[0].data_source
                    else:
                        self.plots[key].data['x'].append(epoch)
                        self.plots[key].data['y'].append(value)
                        cursession().store_objects(self.plots[key])
            push()

    def start_server(self, start_server_flag):
        if BOKEH_AVAILABLE:
            if start_server_flag:
                def preexec_fn():
                    """Prevents the server from dying on training interrupt."""
                    signal.signal(signal.SIGINT, signal.SIG_IGN)
                # Only memory works with subprocess, need to wait for it to start
                log.info('Starting plotting server on %s', self.server_url)
                self.sub = Popen('bokeh-server --ip 0.0.0.0 '
                                 '--backend memory'.split(),
                                 stdout=PIPE, stderr=PIPE, preexec_fn=preexec_fn)
                time.sleep(2)
                log.info('Plotting server PID: {}'.format(self.sub.pid))
            else:
                self.sub = None
            output_server(self.bokeh_doc_name, url=self.server_url)