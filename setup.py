from setuptools import setup
import os

def read_file(filename):
    with open(os.path.join(os.path.dirname(__file__), filename)) as file:
        return file.read()

setup(
    name='automvs',
    version='0.0.7-3',    
    description='Python library for MVS/CE automation',
    url='https://github.com/MVS-sysgen/automvs',
    author='Philip Young',
    author_email='mainframed767@gmail.com',
    license='MIT',
    packages=['automvs'],
    install_requires=[],
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',

    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',    
        'Programming Language :: Python :: 3',
    ],
)
