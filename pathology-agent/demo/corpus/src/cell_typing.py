"""Cell type annotation using the 103-gene Xenium panel.

Leiden clustering at resolution 0.7, then marker-based label assignment.
"""
import scanpy as sc

MARKERS = {"epithelial": ["EPCAM", "KRT8"], "immune": ["PTPRC", "CD3E"],
           "stromal": ["COL1A1", "VIM"], "endothelial": ["PECAM1"]}

def annotate(adata, resolution=0.7):
    sc.pp.neighbors(adata)
    sc.tl.leiden(adata, resolution=resolution)
    return assign_labels(adata, MARKERS)
