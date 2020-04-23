<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Openshift Python Client Packaging](#openshift-python-client-packaging)
  - [Introduction](#introduction)
  - [Recommended Setup](#recommended-setup)
    - [Create User Accounts](#create-user-accounts)
      - [PyPI - The Python Package Index](#pypi---the-python-package-index)
      - [TestPyPI - The Test Python Package Index](#testpypi---the-test-python-package-index)
    - [Generate API Tokens](#generate-api-tokens)
    - [setup.cfg](#setupcfg)
  - [Building](#building)
  - [Publishing](#publishing)
    - [TestPyPI](#testpypi)
    - [PyPI](#pypi)
  - [Installation](#installation)
    - [TestPyPI](#testpypi-1)
    - [PyPI](#pypi-1)
  - [Cleanup](#cleanup)
  - [Helpful Links](#helpful-links)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Openshift Python Client Packaging

## Introduction
This document primarily serves as a reference for us to publish the openshift-client module to PyPI for general consumption by our consumers.  It can also be used by anyone interested in getting started with Python Packaging as all the documented steps and configurations can easily be migrated to any other package/module.

## Recommended Setup
### Create User Accounts
To work with packaging, you will need to create user accounts on one or both of the following sites:  

#### PyPI - The Python Package Index
For **official** releases that are available for installation
* https://pypi.org/

#### TestPyPI - The Test Python Package Index
For **testing** python packaging without impacting the official index
* https://test.pypi.org/

### Generate API Tokens 
For each account that you create, you can generate API Tokens that make publishing your packages/modules easier.  Once the tokens have been generated, you can add them to your `~/.pypirc` file:

```text
[pypi]
username = __token__
password = pypi-<API TOKEN>

[testpypi]
repository: https://test.pypi.org/legacy/
username = __token__
password = pypi-<API TOKEN>
```

### setup.cfg
The openshift-client module has been tested to support both python2 and python3.  Therefore, elect to build a `univeral` wheel instead of platform specific wheels.  To do so, we have added the necessary flags to our `setup.cfg` file:
```text
[bdist_wheel]
universal = 1 

[metadata]
license_file = LICENSE
```

The alternative is to add the necessary flag to the commandline when building your packages:

```bash
    python setup.py build bdist_wheel --universal
```

## Building
For openshift-client, build both a source distribution and a universal wheel: 
```bash
    python setup.py build sdist bdist_wheel
```

## Publishing
Publishing to either package index is accomplished by using [Twine](https://pypi.org/project/twine/).  Because we setup our local `~/.pypirc` above, we can reference the repository by the name defined therein instead of passing the full URL on the commandline.

### TestPyPI
```bash
    twine upload --repository testpypi dist/*
```

### PyPI
```bash
    twine upload --repository pypi dist/*
```

## Installation

### TestPyPI
Installation from TestPyPI must be performed using one of the following methods: 

1. Latest version
```bash
    pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple openshift-client
```
2. Specific version
```bash
    pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple openshift-client==1.0.2
```

### PyPI
1. Latest version
```bash
    pip install openshift-client
```

2. Specific version
```bash
    pip install openshift-client==1.0.2
```

## Cleanup
If you're working on changes, you'll need to bump the version string for every publish to either index (releases are unique).  To cleanup the artifacts from previous builds, you can execute the following: 
```bash
    rm -rf dist/ packages/openshift_client.egg-info/ build/
```

## Helpful Links
* https://packaging.python.org/guides/distributing-packages-using-setuptools/
* https://setuptools.readthedocs.io/en/latest/index.html
* https://packaging.python.org/guides/single-sourcing-package-version/
* https://packaging.python.org/guides/using-testpypi/
* https://packaging.python.org/tutorials/packaging-projects/
* https://github.com/pypa/sampleproject
* https://realpython.com/pypi-publish-python-package/
* https://the-hitchhikers-guide-to-packaging.readthedocs.io/en/latest/index.html