"""pytest bootstrap — supply the required Connect identity environment variables.

``config.py`` reads ``INSTANCE_ALIAS`` / ``INSTANCE_ID`` / ``ASSISTANT_ID`` from
the environment and raises ``ConfigError`` when any of them is missing, so the
suite would fail at import time in a shell that has not sourced the repo-root
``.env``. The tests only ever SYNTHESIZE CloudFormation templates — they never
call AWS — so placeholder ids are sufficient and keep the suite hermetic.

``setdefault`` means a value you have already exported still wins, so running
the suite against your own instance ids works unchanged.

pytest imports the rootdir ``conftest.py`` before collecting any test module,
which is what makes this run early enough.
"""

import os

os.environ.setdefault("INSTANCE_ALIAS", "test-connect-instance")
os.environ.setdefault("INSTANCE_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("ASSISTANT_ID", "11111111-1111-1111-1111-111111111111")
