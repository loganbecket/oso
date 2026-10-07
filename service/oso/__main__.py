"""`python -m oso ...` runs the same commands as `oso ...`; the scheduled check uses it with the windowless
Python on Windows, so no command window flashes up every 15 minutes."""

import sys

from .cli import main

sys.exit(main())
