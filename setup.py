from setuptools import setup, find_packages

setup(
    setup_requires=['pbr'],
    packages=find_packages('src'),
    pbr=True,
)
