#!/usr/bin/env python3
"""
Allow the package to be run as a module: python -m apple_music_manager
"""

from .main import cli

if __name__ == '__main__':
    cli()