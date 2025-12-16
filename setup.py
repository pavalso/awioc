from setuptools import setup
from pathlib import Path

def parse_requirements(filename):
    return [line.strip() for line in Path(filename).read_text().splitlines()
            if line.strip() and not line.startswith("#")]

setup(
    install_requires=parse_requirements("requirements.txt"),
    extras_require={"dev": parse_requirements("requirements-test.txt")}
)
