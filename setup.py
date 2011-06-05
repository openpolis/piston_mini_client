#!/usr/bin/env python

from distutils.core import setup

setup(name='piston-mini-client',
    version='0.3',
    description='A small package to consume Django-Piston web services',
    url='https://launchpad.net/piston-mini-client',
    author='Anthony Lenton',
    author_email='anthony.lenton@canonical.com',
    packages=['piston_mini_client'],
    license='LGPLv3',
    install_requires=[
        'oauth',
        'httplib2',
        'simplejson',
    ],
)
