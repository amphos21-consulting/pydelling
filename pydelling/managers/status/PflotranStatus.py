"""
This class reads a pflotran status file and extracts some key information.


"""

from .BaseStatus import BaseStatus
import logging
import re

logger = logging.getLogger(__name__)

class PflotranStatus(BaseStatus):
    """Parse PFLOTRAN status output for progress and completion signals.

    Category: PFLOTRAN status.
    Tags: pflotran, status, progress, wall-clock, timestep.
    Use when: an MCP agent needs to inspect PFLOTRAN run status files and infer
        current simulation time, timestep history, or completion.
    """

    def __init__(self,
                 status_file,
                 total_time=None):
        """Read a PFLOTRAN status file and extract key progress metrics.

        Category: PFLOTRAN status.
        Tags: pflotran, status-file, initialization.
        Use when: creating a status object for an existing PFLOTRAN run log.
        Args:
            status_file: Path to the PFLOTRAN status file.
            total_time: Optional expected final simulation time used to compute
                progress.
        Side effects:
            Reads status data through ``BaseStatus`` and populates ``times``,
            ``dts``, and ``wall_clock_time``.
        """
        super().__init__(status_file)
        self.times = []
        self.dts = []
        self.wall_clock_time = None
        self.total_time = total_time
        self.extract_key_information()

    def extract_key_information(self):
        """Extract time, timestep, and wall-clock values from status text.

        Category: PFLOTRAN status.
        Tags: pflotran, regex, timestep, wall-clock.
        Use when: refreshing derived PFLOTRAN progress metrics after reading a
            status file.
        Side effects:
            Appends parsed simulation times and timesteps and sets
            ``wall_clock_time`` when present.
        """

        # Search for total Time and Dt values
        pattern = re.compile(r"== REACTIVE TRANSPORT =+.*?Step.*?Time=\s+([\d\.E\+\-]+).*?Dt=\s+([\d\.E\+\-]+)",
                             re.DOTALL)
        matches = pattern.findall(self.status_data)
        for match in matches:
            self.times.append(float(match[0]))
            self.dts.append(float(match[1]))

        # Search for Wall Clock Time value
        pattern = re.compile(r"Wall Clock Time:\s+([\d\.E\+\-]+)")
        match = pattern.search(self.status_data)
        if match:
            self.wall_clock_time = float(match.group(1))

    @property
    def progress(self):
        """Return normalized simulation progress.

        Category: PFLOTRAN status.
        Tags: pflotran, progress, total-time.
        Use when: reporting status as a fraction of configured total simulation
            time.
        Returns:
            float | None: Last parsed time divided by ``total_time``, or
            ``None`` when no total time is configured.
        """
        if self.total_time is None:
            return None
        return self.times[-1] / self.total_time

    @property
    def is_done(self):
        """Return whether the status file contains wall-clock completion data.

        Category: PFLOTRAN status.
        Tags: pflotran, completion, wall-clock.
        Use when: checking whether a PFLOTRAN run has reached a completed status
            marker.
        Returns:
            bool: ``True`` when ``wall_clock_time`` has been parsed.
        """
        if self.wall_clock_time is None:
            return False
        else:
            return True

    def add_total_time(self, total_time):
        """Set the expected total simulation time.

        Category: PFLOTRAN status.
        Tags: pflotran, progress, total-time.
        Use when: progress should be computed after construction.
        Args:
            total_time: Final simulation time used as the denominator for
                ``progress``.
        Side effects:
            Updates ``self.total_time``.
        """
        self.total_time = total_time

    def read(self, status_file = None):
        """Re-read a PFLOTRAN status file and refresh parsed metrics.

        Category: PFLOTRAN status.
        Tags: pflotran, status-file, refresh.
        Use when: polling a running PFLOTRAN simulation for updated status.
        Args:
            status_file: Optional replacement status-file path.
        Side effects:
            Updates ``self.status_file``, reloads status text, and extracts key
            information again.
        """
        self.status_file = status_file if status_file is not None else self.status_file
        self.read_status_file()
        self.extract_key_information()
