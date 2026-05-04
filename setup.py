from setuptools import find_packages, setup

setup(
    name="matplobbot-shared",
    version="0.1.299",  # Bump version
    packages=find_packages(include=["shared_lib", "shared_lib.*"]),
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
        "Pillow>=12.2.0",
        "markdown-it-py",
        "mdit-py-plugins",
        "opentelemetry-api>=1.41.0,<2",
        "opentelemetry-exporter-otlp-proto-http>=1.41.0,<2",
        "opentelemetry-instrumentation-aiohttp-client>=0.62b0,<1",
        "opentelemetry-sdk>=1.41.0,<2",
    ],
    # ВАЖНОЕ ИЗМЕНЕНИЕ ЗДЕСЬ:
    package_data={
        "shared_lib": ["locales/*.json", "templates/*.tex"],
    },
    include_package_data=True,
    python_requires=">=3.11",
)
