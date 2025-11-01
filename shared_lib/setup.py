from setuptools import setup, find_packages

setup(
    name="matplobbot-shared",  # The name you use to `pip install`
    version="0.1.23",
    packages=['shared_lib', 'shared_lib.services', 'shared_lib.locales'], # Explicitly list packages
    description="Shared library for the Matplobbot ecosystem (database, services, i18n).",
    author="Ackrome",
    author_email="ivansergeyevich@gmail.com",
    # Declare dependencies for this library
    install_requires=[
        "asyncpg>=0.30.0",
        "aiohttp>=3.13.2", # Specify versions as needed
        "certifi>=2025.10.5"
    ],
    # This tells setuptools that the package data (like .json files) should be included
    package_data={
        'shared_lib.locales': ['*.json'],
    },
    include_package_data=True,
    python_requires='>=3.11',
)
