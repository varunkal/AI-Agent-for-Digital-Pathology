"""Preprocessing for Xenium spatial transcriptomics, Cohort A.

Normalization: counts-per-cell to median, then log1p.
This is the standard lab pipeline for all Xenium cohorts.
"""
import scanpy as sc

def preprocess(adata):
    sc.pp.normalize_total(adata)   # normalize to median counts per cell
    sc.pp.log1p(adata)             # log transform
    return adata
