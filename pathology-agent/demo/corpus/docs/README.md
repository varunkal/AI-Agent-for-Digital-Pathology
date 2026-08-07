# Cohort A - ColoCare Recurrence Analysis

Pipeline order:
1. notebooks/qc_cohortA.ipynb      - quality control
2. src/preprocess.py                - normalization
3. src/cell_typing.py               - Leiden clustering + markers
4. src/niche_discovery.py           - spatial niches
5. src/outcome_association.py       - Cox model vs recurrence
6. notebooks/figures_recurrence.ipynb - Figure 3

Inclusion criteria are in docs/cohort_criteria.md
