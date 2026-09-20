/**
 * Static model evaluation results, mirrored 1:1 from the evaluation artifacts.
 *
 * Source of truth (regenerate with `python -m ml.evaluate ...` /
 * `ml.evaluate_external.py`, never edit the numbers here by hand):
 *   - artifacts/metrics.json                          (internal held-out test split)
 *   - artifacts/external_test/external_metrics.json   (independent external test set)
 *   - artifacts/external_test/audit.json              (duplicate / leakage audit)
 *   - models/model_meta.json                          (architecture, version)
 *
 * `scripts/check_metrics_consistency.py` re-reads those JSON files and fails if any
 * value below drifts from them.
 *
 * Honesty notes that must stay attached to these numbers:
 *   - the external set was evaluated once with the frozen `best_model.pt`; nothing was
 *     retrained or re-thresholded afterwards;
 *   - 0 byte-identical images are shared between the external set and train/val/test,
 *     but the two sets differ in provenance, so part of the drop cannot be attributed;
 *   - no probability calibration was applied (calibration: NOT IMPLEMENTED).
 */

export interface EvaluationMetrics {
  n: number;
  accuracy: number;
  precision: number;
  recall: number;
  specificity: number;
  f1: number;
  rocAuc: number;
  prAuc: number;
  confusion: { tp: number; tn: number; fp: number; fn: number };
}

/** Held-out internal test split (270 images), evaluated once. */
export const INTERNAL_TEST: EvaluationMetrics = {
  n: 270,
  accuracy: 0.9296296296296296,
  precision: 0.9008264462809917,
  recall: 0.9396551724137931,
  specificity: 0.922077922077922,
  f1: 0.9198312236286921,
  rocAuc: 0.9828145991939096,
  prAuc: 0.979674348832334,
  confusion: { tp: 109, tn: 142, fp: 12, fn: 7 },
};

/** Independent external test set (797 images, benign 400 / malignant 397). */
export const EXTERNAL_TEST: EvaluationMetrics = {
  n: 797,
  accuracy: 0.7854454203262233,
  precision: 0.8843537414965986,
  recall: 0.654911838790932,
  specificity: 0.915,
  f1: 0.7525325615050651,
  rocAuc: 0.907852644836272,
  prAuc: 0.8929252898408199,
  confusion: { tp: 260, tn: 366, fp: 34, fn: 137 },
};

/** Byte-level overlap between the external test set and each internal split. */
export const EXTERNAL_OVERLAP = { train: 0, val: 0, test: 0 };

export const EXTERNAL_CLASS_BALANCE = { benign: 400, malignant: 397 };

export const MODEL_INFO = {
  architecture: 'resnet50',
  modelVersion: '1.0.0+run_a_resnet50',
  inputSize: 224,
  calibration: 'NOT IMPLEMENTED',
  reportedAccuracyTarget: 0.9,
};

/** Absolute percentage-point difference between two rates. */
export function pointDelta(a: number, b: number): number {
  return (a - b) * 100;
}
