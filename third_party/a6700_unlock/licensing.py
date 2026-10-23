"""License notices available offline in both source and installed packages."""
from importlib.resources import files

from . import __version__


def display(full=False, third_party=False):
    root = files("a6700_unlock").joinpath("data/legal")
    if full:
        print(root.joinpath("LICENSE.txt").read_text(encoding="utf-8"), end="")
    elif third_party:
        print(root.joinpath("THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"), end="")
    else:
        print(root.joinpath("NOTICE.txt").read_text(encoding="utf-8"), end="")
        print(f"对应源码包：a6700-unlock-{__version__}-source.zip")
        print("完整许可：a6700-unlock license --full")
        print("第三方归属：a6700-unlock license --third-party")
