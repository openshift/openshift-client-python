#!/usr/bin/python

import os
from setuptools import setup, find_packages


def get_requirements(filename="requirements.txt"):
    """Extract requirements from a pip formatted requirements file."""

    with open(filename, "r") as requirements_file:
        return requirements_file.read().splitlines()


def get_long_description():
    """Returns README.md content."""
    return open("README.md", "r").read()


def read(rel_path):
    """Returns the contents of the file at the specified relative path."""
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, rel_path), 'r') as fp:
        return fp.read()


def get_version(rel_path):
    """Returns the semantic version for the openshift-client module."""
    for line in read(rel_path).splitlines():
        if line.startswith('__VERSION__'):
            delim = '"' if '"' in line else "'"
            return line.split(delim)[1]
    else:
        raise RuntimeError("Unable to find version string.")


setup(
    name="openshift-client",
    version=get_version('packages/openshift/__init__.py'),
    author="Justin Pierce",
    author_email="jupierce@redhat.com",
    maintainer="Brad Williams",
    maintainer_email="brawilli@redhat.com",
    url="https://github.com/openshift/openshift-client-python",
    description="OpenShift python client",
    packages=find_packages(where='packages'),
    package_dir={"": "packages"},
    install_requires=get_requirements(),
    keywords=["OpenShift"],
    include_package_data=True,
    data_files=[
        ("requirements.txt", ["requirements.txt"]),
    ],
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Utilities",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
    ],
)
