#!/usr/bin/env python3
"""Punto di ingresso di Edunews24 AI Visibility Monitor.

    python sender.py serve             # API + scheduler (comando del container)
    python sender.py run-once          # un ciclo immediato, per test
    python sender.py generate-queries  # genera query senza inviarle
    python sender.py sync-topics       # aggiorna lo snapshot dei topic
    python sender.py cost-report       # spesa stimata

Volutamente sottile: la logica sta in `app/cli.py`.
"""

from __future__ import annotations

import sys

from app.cli import main

if __name__ == "__main__":
    sys.exit(main())
