from setuptools import setup, find_packages

setup(
    name="matplobbot-shared",
    version="0.1.40", # Let's use the version from your requirements.txt
    packages=find_packages(include=['shared_lib', 'shared_lib.*']),
    description="Shared library for the Matplobbot ecosystem (database, services, i18n).",
    author="Ackrome",
    author_email="ivansergeyevich@gmail.com",
    # Declare dependencies for this library
    install_requires=[
        "asyncpg",
        "aiohttp", # Specify versions as needed
        "certifi",
        "redis"
    ],
    # This tells setuptools that the package data (like .json files) should be included
    package_data={
        'shared_lib.locales': ['*.json'],
    },
    include_package_data=True,
    python_requires='>=3.11',
)
