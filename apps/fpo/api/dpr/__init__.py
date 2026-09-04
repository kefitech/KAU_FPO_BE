"""
DPR API endpoints — one module per data element.

Naming convention: <data_element_slug>.py — e.g. raw_material.py, machinery.py.
Each module exposes:
  - Serializer(s) for the data element
  - View class(es) for GET/PATCH
  - Any data-element-specific helpers

URLs mounted at /api/fpo/dpr/ via apps/fpo/api/dpr/urls.py

Spec: context/phase2/Dpr/Data Collection Module V1.0.pdf
Plan: context/phase2/Dpr/BUILD_PLAN.md
Context: context/phase2/Dpr/DPR_V2_CONTEXT.md
"""
