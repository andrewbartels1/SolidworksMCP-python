# Configuration file for Sphinx documentation
# Generated for SolidWorks MCP Server

import os
import sys
from pathlib import Path

# Add source directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Project information
project = "SolidWorks MCP Server"
copyright = "2026, SolidWorks MCP Contributors"
author = "SolidWorks MCP Team"
release = "1.0.0"

# Extensions
extensions = [
    "sphinx.ext.autodoc",  # Automatic API documentation
    "sphinx.ext.autosummary",  # Summary tables
    "sphinx.ext.intersphinx",  # Links to other projects
    "sphinx.ext.viewcode",  # Links to source code
    "sphinx.ext.napoleon",  # Google/NumPy docstring support
    "sphinx_rtd_theme",  # ReadTheDocs theme
    "sphinx.ext.coverage",  # Coverage analysis
    "sphinx.ext.mathjax",  # Math support
]

# Autodoc configuration
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "show-inheritance": True,
    "inherited-members": True,
    "ignore-module-all": False,
}

# Napoleon extension configuration (Google docstring support)
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

# Autosummary configuration
autosummary_generate = True
autosummary_generate_overwrite = True

# HTML theme
html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "analytics_id": "",
    "canonical_url": "",
    "collapse_navigation": True,
    "display_version": True,
    "logo_only": False,
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    "vcs_pageview_mode": "",
    "style_nav_header_background": "#2980B9",
    "logo": "logo.png",
}

# Output paths
html_static_path = ["_static"]
templates_path = ["_templates"]

# Source suffix
source_suffix = {".rst": None}

# Exclude patterns
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "**/__pycache__",
    "**/*.pyc",
]

# ReadTheDocs settings
master_doc = "index"

# Syntax highlighting
pygments_style = "sphinx"

# Custom settings for code documentation
highlight_language = "python3"
