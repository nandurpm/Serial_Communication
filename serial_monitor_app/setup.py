#!/usr/bin/env python3
"""Packaging configuration for Serial Communication Monitor."""

from pathlib import Path

from setuptools import find_packages, setup

BASE_DIR = Path(__file__).resolve().parent

setup(
    name="serial-monitor",
    version="1.1.0",
    author="Nandakumar M",
    description="Cross-platform serial communication and Modbus RTU monitoring application",
    long_description=(BASE_DIR / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    py_modules=["app_gui", "app_cli", "app_api"],
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows :: Windows 10",
        "Operating System :: Microsoft :: Windows :: Windows 11",
        "Operating System :: POSIX :: Linux",
        "Topic :: System :: Monitoring",
    ],
    python_requires=">=3.9",
    install_requires=[
        "pyserial>=3.5,<4",
        "Flask>=2.3,<4",
        "Flask-Cors>=4,<7",
        "Flask-RESTful>=0.3.10,<1",
    ],
    extras_require={
        "charts": ["matplotlib>=3.7,<4", "numpy>=1.24,<3", "pandas>=2,<3"],
        "dev": ["pytest>=7,<9", "black>=23,<26", "flake8>=6,<8"],
        "build": ["pyinstaller==6.16.0"],
    },
    entry_points={
        "console_scripts": [
            "serial-monitor-gui=app_gui:main",
            "serial-monitor-cli=app_cli:main",
            "serial-monitor-api=app_api:main",
        ]
    },
)
