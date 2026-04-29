"""``python -m z4j_django`` - module entry point.

Both forms work and dispatch to the same code:

    z4j-django <subcommand>            # pip-installed console script
    python -m z4j_django <subcommand>  # module form
    python manage.py z4j_<subcommand>  # Django-native management command

The standalone forms (``z4j-django`` and ``python -m z4j_django``)
read ``Z4J_*`` env vars only - they intentionally don't load
``DJANGO_SETTINGS_MODULE``. To pick up config from Django settings
use ``manage.py z4j_doctor`` etc. instead. Both surfaces ship from
1.1.2 onward.
"""

from __future__ import annotations

import sys

from z4j_django.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
