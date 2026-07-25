"""Eval suite — execution-accuracy runner for the agentic loop.

Two datasets share one runner:
  - custom: hand-crafted NL/SQL pairs on data/sample_dbs/ecommerce.sqlite
  - bird:   sampled BIRD-SQL dev items (fetched on demand)

Metric is execution accuracy (EX): run predicted SQL, run gold SQL, compare
result sets. This is the number v3 (multi-model bench) and v4 (LoRA fine-tune)
will move.
"""
