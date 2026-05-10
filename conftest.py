"""
Root conftest.py — ensures the project root is always on sys.path.

This file is picked up by pytest automatically before any test runs.
It fixes "ModuleNotFoundError" when running pytest from any directory.
"""
import sys
import os

# Make sure project root is always importable
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)
