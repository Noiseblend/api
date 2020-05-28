# pylint: skip-file
from io import open

from setuptools import find_packages, setup

with open("noiseblend_api/__init__.py", "r") as f:
    for line in f:
        if line.startswith("__version__"):
            version = line.strip().split("=")[1].strip(" '\"")
            break
    else:
        version = "0.0.1"

with open("README.md", "r", encoding="utf-8") as f:
    readme = f.read()

REQUIRES = [
    "aiodns",
    "aiohttp>=3.0.9",
    "aioredis",
    "async_generator",
    "asyncpg",
    "cchardet",
    "fuzzywuzzy",
    "honcho",
    "kick",
    "pony",
    "psycopg2-binary",
    "pycountry",
    "python-dateutil",
    "sanic",
    "sanic-plugins-framework",
    "sanic_compress",
    "sanic_cors",
    "sendgrid",
    "sentry_sdk",
    "spfy>=3.8.5",
    "stringcase",
]

setup(
    name="noiseblend_api",
    version=version,
    description="",
    long_description=readme,
    author="Alin Panaitiu",
    author_email="alin.panaitiu@gmail.com",
    maintainer="Alin Panaitiu",
    maintainer_email="alin.panaitiu@gmail.com",
    url="https://gitlab.com/alin23/noiseblend-api",
    license="MIT/Apache-2.0",
    keywords=[""],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
    ],
    install_requires=REQUIRES,
    tests_require=["coverage", "pytest"],
    packages=find_packages(),
)
