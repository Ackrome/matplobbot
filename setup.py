from setuptools import find_packages, setup

setup(
    name="matplobbot-shared",
    version="0.1.365",  # Bump version
    packages=find_packages(include=["shared_lib", "shared_lib.*"]),
    description="Shared library for the Matplobbot ecosystem.",
    author="Ackrome",
    author_email="ivansergeyevich@gmail.com",
    install_requires=[
        "asyncpg",
        "aiohttp>=3.14.3,<3.15",
        "certifi",
        "cryptography>=50.0.0,<51",
        "redis",
        "cachetools",
        "celery",
        "Pillow>=12.3.0",
        "pdfplumber==0.11.10",
        "markdown-it-py",
        "mdit-py-plugins",
        "opentelemetry-api>=1.41.0,<2",
        "opentelemetry-exporter-otlp-proto-http>=1.41.0,<2",
        "opentelemetry-instrumentation-aiohttp-client>=0.62b0,<1",
        "opentelemetry-sdk>=1.41.0,<2",
    ],
    # Keep the small numeric recognizer and its integrity metadata in wheels.
    # Its inference runtime is installed only by the scheduler image.
    package_data={
        "shared_lib": [
            "locales/*.json",
            "templates/*.tex",
            "data/curriculum_numeric.onnx",
            "data/curriculum_numeric.json",
        ],
    },
    include_package_data=True,
    python_requires=">=3.11",
)
