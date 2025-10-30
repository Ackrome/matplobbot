from setuptools import setup, find_packages

setup(
    name="matplobbot-shared",  # Use a standard name format
    version="0.1.13", # Or your desired starting version
    packages=find_packages(where="."), # This is correct for setup.py being inside shared_lib/
    description="Shared library for the Matplobbot ecosystem (database, services, i18n).",
    author="Ackrome",
    author_email="ivansergeyevich@gmail.com",
    # Declare dependencies for this library
    install_requires=[
        "asyncpg>=0.28.0",
        "aiohttp>=3.9.0", # Specify versions as needed
        "certifi>=2023.7.22"
    ],
    
    python_requires='>=3.11',
)
