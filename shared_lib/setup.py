from setuptools import setup, find_packages

setup(
    name="matplobbot-shared",  # The name you use to `pip install`
    version="0.1.21",
    packages=['shared_lib', 'shared_lib.services', 'shared_lib.locales'], # Explicitly list packages
    description="Shared library for the Matplobbot ecosystem (database, services, i18n).",
    author="Ackrome",
    author_email="ivansergeyevich@gmail.com",
    # Declare dependencies for this library
    install_requires=[
        "asyncpg",
        "aiohttp", # Specify versions as needed
        "certifi"
    ],
    # This tells setuptools that the package data (like .json files) should be included
    package_data={
        'shared_lib.locales': ['*.json'],
    },
    include_package_data=True,
    python_requires='>=3.11',
)
