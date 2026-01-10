from setuptools import setup, find_packages

setup(
    name="matplobbot-shared",
    version="0.1.76", # Bump version
    packages=find_packages(include=['shared_lib', 'shared_lib.*']),
    description="Shared library for the Matplobbot ecosystem.",
    author="Ackrome",
    author_email="ivansergeyevich@gmail.com",
    install_requires=[
        "asyncpg",
        "aiohttp",
        "certifi",
        "redis",
        "cachetools",
        "celery",
        "Pillow",
        "markdown-it-py",
        "mdit-py-plugins" 
    ],
    # ВАЖНОЕ ИЗМЕНЕНИЕ ЗДЕСЬ:
    package_data={
        'shared_lib': ['locales/*.json', 'templates/*.tex'], 
    },
    include_package_data=True,
    python_requires='>=3.11',
)