from setuptools import setup, find_packages

__description__ = "DSL-driven Spotify control via private API (fork of SpotAPI by Aran)"
__install_require__ = [
    "requests",
    "colorama",
    "readerwriterlock",
    "tls_client",
    "typing_extensions",
    "pyotp",
    "beautifulsoup4",
    "lark",
    "websockets",
]
__extras__ = {}

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="clautify",
    author="shepardxia",
    description=__description__,
    packages=find_packages(),
    package_data={"clautify": ["dsl/grammar.lark"]},
    install_requires=__install_require__,
    extras_require=__extras__,
    keywords=[
        "Spotify",
        "API",
        "Spotify API",
        "Spotify Private API",
        "Follow",
        "Like",
        "Creator",
        "Music",
        "Music API",
        "Streaming",
        "Music Data",
        "Track",
        "Playlist",
        "Album",
        "Artist",
        "Music Search",
        "Music Metadata",
        "SpotAPI",
        "Python Spotify Wrapper",
        "Music Automation",
        "Web Scraping",
        "Python Music API",
        "Spotify Integration",
        "Spotify Playlist",
        "Spotify Tracks",
    ],
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires=">=3.10",
    version="1.2.7",
)
