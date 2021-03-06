"""Module managing errors."""

import logging
import os
import re
import scooby
import sys

import vtk

import pyvista


def set_error_output_file(filename):
    """Set a file to write out the VTK errors."""
    filename = os.path.abspath(os.path.expanduser(filename))
    fileOutputWindow = vtk.vtkFileOutputWindow()
    fileOutputWindow.SetFileName(filename)
    outputWindow = vtk.vtkOutputWindow()
    outputWindow.SetInstance(fileOutputWindow)
    return fileOutputWindow, outputWindow


class Observer:
    """A standerd class for observing VTK objects."""

    def __init__(self, event_type='ErrorEvent', log=True):
        """Initialize observer."""
        self.__event_occurred = False
        self.__message = None
        self.__message_etc = None
        self.CallDataType = 'string0'
        self.__observing = False
        self.event_type = event_type
        self.__log = log

    @staticmethod
    def parse_message(message):
        """Parse the given message."""
        # Message format
        regex = re.compile(r'([A-Z]+):\sIn\s(.+),\sline\s.+\n\w+\s\((.+)\):\s(.+)')
        try:
            kind, path, address, alert = regex.findall(message)[0]
            return kind, path, address, alert
        except:
            return '', '', '', message

    def log_message(self, kind, alert):
        """Parse different event types and passes them to logging."""
        if kind == 'ERROR':
            logging.error(alert)
        else:
            logging.warning(alert)
        return

    def __call__(self, obj, event, message):
        """Declare standard call function for the observer.

        On an event occurrence, this function executes.

        """
        self.__event_occurred = True
        self.__message_etc = message
        kind, path, address, alert = self.parse_message(message)
        self.__message = alert
        if self.__log:
            self.log_message(kind, alert)

    def has_event_occurred(self):
        """Ask self if an error has occurred since last querried.

        This resets the observer's status.

        """
        occ = self.__event_occurred
        self.__event_occurred = False
        return occ

    def get_message(self, etc=False):
        """Get the last set error message.

        Return
        ------
            str: the last set error message

        """
        if etc:
            return self.__message_etc
        return self.__message

    def observe(self, algorithm):
        """Make this an observer of an algorithm."""
        if self.__observing:
            raise RuntimeError('This error observer is already observing an algorithm.')
        if hasattr(algorithm, 'GetExecutive') and algorithm.GetExecutive() is not None:
            algorithm.GetExecutive().AddObserver(self.event_type, self)
        algorithm.AddObserver(self.event_type, self)
        self.__observing = True
        return


def send_errors_to_logging():
    """Send all VTK error/warning messages to Python's logging module."""
    error_output = vtk.vtkStringOutputWindow()
    error_win = vtk.vtkOutputWindow()
    error_win.SetInstance(error_output)
    obs = Observer()
    return obs.observe(error_output)


def get_gpu_info():
    """Get all information about the GPU."""
    # an OpenGL context MUST be opened before trying to do this.
    plotter = pyvista.Plotter(notebook=False, off_screen=True)
    plotter.add_mesh(pyvista.Sphere())
    plotter.show(auto_close=False)
    gpu_info = plotter.ren_win.ReportCapabilities()
    plotter.close()
    # Remove from list of Plotters
    pyvista.plotting._ALL_PLOTTERS.pop(plotter._id_name)
    return gpu_info


class GPUInfo():
    """A class to hold GPU details."""

    def __init__(self):
        """Instantiate a container for the GPU information."""
        self._gpu_info = get_gpu_info()


    @property
    def renderer(self):
        """GPU renderer name."""
        regex = re.compile("OpenGL renderer string:(.+)\n")
        try:
            renderer = regex.findall(self._gpu_info)[0]
        except IndexError:
            raise RuntimeError("Unable to parse GPU information for the renderer.")
        return renderer.strip()


    @property
    def version(self):
        """GPU renderer version."""
        regex = re.compile("OpenGL version string:(.+)\n")
        try:
            version = regex.findall(self._gpu_info)[0]
        except IndexError:
            raise RuntimeError("Unable to parse GPU information for the version.")
        return version.strip()


    @property
    def vendor(self):
        """GPU renderer vendor."""
        regex = re.compile("OpenGL vendor string:(.+)\n")
        try:
            vendor = regex.findall(self._gpu_info)[0]
        except IndexError:
            raise RuntimeError("Unable to parse GPU information for the vendor.")
        return vendor.strip()


    def get_info(self):
        """All GPU information as tuple pairs."""
        return (("GPU Vendor", self.vendor),
                ("GPU Renderer", self.renderer),
                ("GPU Version", self.version),
               )


    def _repr_html_(self):
        """HTML table representation."""
        fmt = "<table>"
        row = "<tr><th>{}</th><td>{}</td></tr>\n"
        for meta in self.get_info():
            fmt += row.format(*meta)
        fmt += "</table>"
        return fmt


    def __repr__(self):
        """Representation method."""
        content = "\n"
        for k, v in self.get_info():
            content += "{:>18}".format(k)+' : {}\n'.format(v)
        content += "\n"
        return content



class Report(scooby.Report):
    """A class for custom scooby.Report."""

    def __init__(self, additional=None, ncol=3, text_width=80, sort=False,
                 gpu=True):
        """Generate a :class:`scooby.Report` instance.

        Parameters
        ----------
        additional : list(ModuleType), list(str)
            List of packages or package names to add to output information.

        ncol : int, optional
            Number of package-columns in html table; only has effect if
            ``mode='HTML'`` or ``mode='html'``. Defaults to 3.

        text_width : int, optional
            The text width for non-HTML display modes

        sort : bool, optional
            Alphabetically sort the packages

        gpu : bool
            Gather information about the GPU. Defaults to ``True`` but if
            experiencing renderinng issues, pass ``False`` to safely generate
            a report.

        """
        # Mandatory packages.
        core = ['pyvista', 'vtk', 'numpy', 'imageio', 'appdirs', 'scooby']

        # Optional packages.
        optional = ['matplotlib', 'PyQt5', 'IPython', 'colorcet',
                    'cmocean', 'panel']

        # Information about the GPU - bare except in case there is a rendering
        # bug that the user is trying to report.
        if gpu:
            try:
                extra_meta = [(t[1], t[0]) for t in GPUInfo().get_info()]
            except:
                extra_meta = ("GPU Details", "error")

        scooby.Report.__init__(self, additional=additional, core=core,
                               optional=optional, ncol=ncol,
                               text_width=text_width, sort=sort,
                               extra_meta=extra_meta)


def assert_empty_kwargs(**kwargs):
    """Assert that all keyword arguments have been used (internal helper).

    If any keyword arguments are passed, a ``TypeError`` is raised.

    """
    n = len(kwargs)
    if n == 0:
        return True
    caller = sys._getframe(1).f_code.co_name
    keys = list(kwargs.keys())
    bad_arguments = "[" + ("{}, " * (n - 1) + "{}").format(*keys) + "]"
    if n == 1:
        grammar = "is an invalid keyword argument"
    else:
        grammar = "are invalid keyword arguments"
    message = "{} {} for `{}`".format(bad_arguments, grammar, caller)
    raise TypeError(message)
