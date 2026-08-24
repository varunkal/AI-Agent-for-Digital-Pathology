"""Shared QC helpers used by every cohort.

House thresholds live here so that all cohorts filter identically. If you change
a value here it changes for every cohort, so check config/ as well: the pipeline
YAML files carry their own copy for the record and the two must agree.
"""

MIN_TRANSCRIPTS_PER_CELL = 10
MIN_CELLS_PER_GENE = 3


def apply_qc(adata, min_counts=MIN_TRANSCRIPTS_PER_CELL, min_cells=MIN_CELLS_PER_GENE):
    import scanpy as sc

    sc.pp.filter_cells(adata, min_counts=min_counts)
    sc.pp.filter_genes(adata, min_cells=min_cells)
    return adata
