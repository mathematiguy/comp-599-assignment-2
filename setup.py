from setuptools import setup, find_packages

setup(
    name="pkg",
    version="0.1",
    packages=find_packages(exclude=["tests*"]),
    description="A python package for manipulating crossref data on a spark cluster",
    url="https://github.com/dragonfly-science/mbie-future-pathways",
    author="Caleb Moses",
    author_email="caleb@dragonfly.co.nz",
    include_package_data=True,
)
