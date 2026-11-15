import os

os.environ.setdefault("ONTOPOC_DEV", "1")   # the tests start services with --no-auth, which is refused without it
