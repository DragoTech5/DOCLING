#!/usr/bin/env python3
"""
Minimal startup script that removes Railway's PORT variable before any imports.
This ensures uvicorn never sees an invalid PORT value.
"""

import os
import sys

# CRITICAL: Remove PORT before ANY other imports
if "PORT" in os.environ:
    del os.environ["PORT"]

# Now safe to import and run uvicorn
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8200,
        log_level="info",
    )
