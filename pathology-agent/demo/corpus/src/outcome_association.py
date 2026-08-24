"""Association between spatial niche abundance and recurrence.

Statistical test: Cox proportional hazards, adjusted for stage and age.
Multiple testing correction: Benjamini-Hochberg across the 8 niches.
"""
from lifelines import CoxPHFitter

def test_association(niche_abundance, outcomes):
    cph = CoxPHFitter()
    cph.fit(merged, duration_col="time_to_recurrence", event_col="recurred")
    return cph.summary
