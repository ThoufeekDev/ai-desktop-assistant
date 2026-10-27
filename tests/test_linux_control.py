
"""Tests for safe Linux desktop controls."""

import subprocess
import unittest
from unittest.mock import patch

from jarvis.app_discovery import DesktopApplication
from jarvis.linux_control import LinuxControl


class LinuxControlTests(unittest.TestCase):
    @patch("jarvis.linux_control.subprocess.Popen")
    @patch("jarvis.linux_control.shutil.which")
    @patch("jarvis.linux_control.ApplicationDiscovery")
    def test_opens_discovered_application(
        self,
        discovery_class,
        which,
        popen,
    ) -> None:
        discovery_class.return_value.search.return_value = [
            DesktopApplication(
                name="Example Browser",
                desktop_id="example-browser.desktop",
            )
        ]
        which.return_value = "/usr/bin/gtk-launch"

        control = LinuxControl()
        result = control.open_app("Example Browser")

        self.assertEqual(result, "Opened Example Browser.")
        popen.assert_called_once_with(
            ["/usr/bin/gtk-launch", "example-browser"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    @patch("jarvis.linux_control.subprocess.Popen")
    @patch("jarvis.linux_control.shutil.which")
    @patch("jarvis.linux_control.ApplicationDiscovery")
    def test_does_not_launch_when_application_is_not_found(
        self,
        discovery_class,
        which,
        popen,
    ) -> None:
        discovery_class.return_value.search.return_value = []

        control = LinuxControl()
        result = control.open_app("Unknown Application")

        self.assertIn("couldn't find", result.lower())
        which.assert_not_called()
        popen.assert_not_called()

    @patch("jarvis.linux_control.subprocess.Popen")
    @patch("jarvis.linux_control.shutil.which")
    @patch("jarvis.linux_control.ApplicationDiscovery")
    def test_does_not_launch_when_gtk_launch_is_missing(
        self,
        discovery_class,
        which,
        popen,
    ) -> None:
        discovery_class.return_value.search.return_value = [
            DesktopApplication(
                name="Example Browser",
                desktop_id="example-browser.desktop",
            )
        ]
        which.return_value = None

        control = LinuxControl()
        result = control.open_app("Example Browser")

        self.assertIn("gtk-launch", result)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
