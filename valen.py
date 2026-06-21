#!/usr/bin/env python3
"""Compat shim: `python valen.py` continua funcionando.

Após instalar (`pip install .`), prefira o comando `valenor`.
After install, prefer the `valenor` command.
"""

from valenor.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
