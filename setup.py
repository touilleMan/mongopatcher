# -*- coding: utf-8 -*-
import re
from setuptools import setup, find_packages


REQUIRES = (
    'pymongo>=2.8'
)


def read(fname):
    with open(fname) as fp:
        content = fp.read()
    return content

setup(
    name='mongopatcher',
    version='0.3.0',
    description='Mongodb incremental migration tool',
    long_description=read('README.rst'),
    author='Emmanuel Leblond',
    author_email='emmanuel.leblond@gmail.com',
    url='https://github.com/touilleMan/mongopatcher',
    packages=find_packages(exclude=("test*", )),
    package_dir={'mongopatcher': 'mongopatcher'},
    include_package_data=True,
    install_requires=REQUIRES,
    license='MIT',
    zip_safe=False,
    keywords='mongoengine',
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    test_suite='tests',
)
