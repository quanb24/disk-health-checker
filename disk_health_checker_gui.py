"""PyInstaller entry point for the GUI.

This thin wrapper exists so PyInstaller has a single .py file to target.
It simply calls the GUI's main function.
"""
from disk_health_checker.gui.app import main

main()
