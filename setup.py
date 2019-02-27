from setuptools import setup, find_packages
from os import path

import codecs

here = path.abspath(path.dirname(__file__))


def long_description():
    with codecs.open('README.rst', encoding='utf8') as f:
        return f.read()


setup(
    name='lemontest',
    version='0.2.0',
    description='A unittest runner for detecting lemon tests',
    long_description=long_description(),
    url='https://github.com/willemt/lemontest',
    author='willemt',
    author_email='himself@willemthiart.com',
    license='BSD',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: System :: Logging',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    keywords='development testing',
    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
    install_requires=['gitpython'],
    package_data={},
    data_files=[],
    entry_points={
        'console_scripts': [
        ],
    },
)
