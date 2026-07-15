#!/usr/bin/env python3
"""
Setup script for Serial Communication Monitor
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="serial-monitor",
    version="1.0.0",
    author="Your Name",
    description="Linux Serial Communication Monitoring Application",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Topic :: System :: Monitoring",
    ],
    python_requires=">=3.6",
    install_requires=[
        "pyserial>=3.5",
        "modbus-tk>=1.2.0",
        "Flask>=2.3.0",
        "numpy>=1.20",
        "pandas>=1.0",
        "matplotlib>=3.0",
    ],
    entry_points={
        "console_scripts": [
            "serial-monitor-gui=app_gui:main",
            "serial-monitor-cli=app_cli:main",
            "serial-monitor-api=app_api:main",
        ],
    },
)
