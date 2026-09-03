# Inter-annotator Agreement and Statistical Diagnostics

For two independent categorical raters A and B on the **same aligned records**:

\[\kappa = \frac{p_o-p_e}{1-p_e}\]

Here `p_o` is the fraction of jointly eligible examples with exactly matching class labels. `p_e` is the expected matching fraction under independent draws from the raters' observed marginal distributions. `cohen_kappa_score(y_A, y_B, labels=ontology_order)` from scikit-learn implements kappa; output is cross-checked against raw agreement and marginals. The confusion matrix rows are A, columns B in `configs/annotation.yaml` order.

The denominator is jointly annotated *valid, distinct* task IDs. The excluded denominator is all eligible validated source records. If no pairs remain, both raw agreement and kappa are `null`; if `p_e=1`, raw agreement may be 100% but kappa is undefined, **not** automatically 1. A label absent in both raters has no defined class-conditional observed agreement. Strong prevalence imbalance can make raw agreement deceptively high relative to kappa.

**Per-class diagnostics:** `both_selected`, `at_least_one_selected`, `disagreements`, and agreement conditional on a label being mentioned. This is not precision/recall against gold labels. `by_category` and `by_source` recompute pairwise scores over each valid subgroup. Optional raw-agreement percentile bootstrap draws samples with replacement, fixed seed 2026; bootstrap intervals do not fix systematic annotator bias.

**More than two annotators:** pairwise kappa is separately calculated for every eligible rater pair via `evaluate_all_pairs`. It is never described as a multi-rater global score. Multi-rater coefficients such as Krippendorff's alpha are outside the present core and require explicit handling of incomplete panels and measurement levels.

**Weighted kappa:** for an inherently ordinal new ontology, explicitly declare `--ordinal` and choose linear/quadratic weights. Weighting on default nominal sentiment categories is scientifically unsupported. Do not interpret any kappa threshold as universal proof of acceptable annotation correctness. Consider expert gold checks and per-class confusion diagnostics.

Test fixtures contain synthetic annotation results for arithmetic verification only. Real results should be reported only after independent human labeling and trusted export synchronization.
