"""Backend package initialization - sets up sys.path for imports."""

import os
import sys

# Make the backend directory itself and workspace root importable
backend_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.dirname(backend_dir)

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

