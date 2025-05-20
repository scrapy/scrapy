from setuptools import setup, find_packages

setup(
    name="scrapy-priority-scheduler",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "scrapy>=2.13.0",
    ],
    entry_points={
        "scrapy": [
            "scheduler = scrapy_priority_scheduler.scheduler:PriorityScheduler",
        ],
    },
    author="Your Name",
    author_email="your.email@example.com",
    description="A Scrapy scheduler that prioritizes branch requests over leaf requests",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/scrapy-priority-scheduler",
    license="BSD-3-Clause",
)
