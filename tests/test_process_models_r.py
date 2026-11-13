"""Stage 37 (Issue #66): an optional cross-check of the path models in R.

Skipped unless ``Rscript`` and the R package ``lavaan`` are installed (for
example ``apt-get install r-base-core r-cran-lavaan``); CI never requires R.

R computes, independently of Python:
* every path of Model 4 (two mediators, two covariates) and Model 1 with base
  R ``lm`` — coefficients and classical standard errors; the conditional
  effect of X at W from ``vcov``;
* the percentile bootstrap of each indirect effect with ``lm.fit`` on the
  SAME resample indices (written by Python, 1-based in R) and
  ``quantile(type = 7)``;
* the Model 4 paths as a lavaan path model (ML estimates of a recursive
  model with these regressions equal the OLS coefficients) and the defined
  parameters a·b.

Tolerances: lm and the bootstrap 1e-8 relative (different linear algebra,
same estimator); lavaan 1e-5 relative (iterative ML).
Only fictional, simulated data appear here.
"""

from __future__ import annotations

import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402

from process_models import ProcessSpec, fit_process  # noqa: E402
from test_process_models import complete, synthetic  # noqa: E402

RSCRIPT = shutil.which("Rscript")


def _has_lavaan() -> bool:
    if RSCRIPT is None:
        return False
    try:
        done = subprocess.run([RSCRIPT, "-e", "quit(status = !requireNamespace('lavaan', "
                                              "quietly = TRUE))"],
                              capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


R_SCRIPT = r"""
args <- commandArgs(trailingOnly = TRUE)
d <- read.csv(args[1])
idx <- as.matrix(read.csv(args[2], header = FALSE))
out <- function(key, value) cat(key, sprintf("%.17g", value), "\n")
fa1 <- lm(m1 ~ x + age + employed, data = d)
fa2 <- lm(m2 ~ x + age + employed, data = d)
fy <- lm(y ~ x + m1 + m2 + age + employed, data = d)
ft <- lm(y ~ x + age + employed, data = d)
for (nm in names(coef(fy))) { out(paste0("y:", nm), coef(fy)[nm]);
                              out(paste0("y_se:", nm), sqrt(diag(vcov(fy)))[nm]) }
out("a1", coef(fa1)["x"]); out("a1_se", sqrt(diag(vcov(fa1)))["x"])
out("a2", coef(fa2)["x"]); out("total", coef(ft)["x"])
X1 <- cbind(1, d$x, d$age, d$employed)
XY <- cbind(1, d$x, d$m1, d$m2, d$age, d$employed)
boot1 <- numeric(nrow(idx)); boot2 <- numeric(nrow(idx))
for (r in seq_len(nrow(idx))) {
  i <- idx[r, ] + 1
  a1 <- lm.fit(X1[i, ], d$m1[i])$coefficients[2]
  a2 <- lm.fit(X1[i, ], d$m2[i])$coefficients[2]
  b <- lm.fit(XY[i, ], d$y[i])$coefficients
  boot1[r] <- a1 * b[3]; boot2[r] <- a2 * b[4]
}
q1 <- quantile(boot1, c(0.025, 0.975), type = 7); q2 <- quantile(boot2, c(0.025, 0.975), type = 7)
out("ci1_low", q1[1]); out("ci1_high", q1[2]); out("ci2_low", q2[1]); out("ci2_high", q2[2])
fm <- lm(y ~ x * w + age + employed, data = d)
v <- vcov(fm); b <- coef(fm)
w0 <- mean(d$w) + sd(d$w)
out("b3", b["x:w"]); out("theta_plus", b["x"] + b["x:w"] * w0)
out("theta_plus_se", sqrt(v["x", "x"] + w0^2 * v["x:w", "x:w"] + 2 * w0 * v["x", "x:w"]))
suppressPackageStartupMessages(library(lavaan))
model <- '
  m1 ~ a1*x + age + employed
  m2 ~ a2*x + age + employed
  y ~ b1*m1 + b2*m2 + cp*x + age + employed
  ind1 := a1*b1
  ind2 := a2*b2
'
fit <- sem(model, data = d)
pe <- parameterEstimates(fit)
for (lab in c("a1", "a2", "b1", "b2", "cp", "ind1", "ind2")) out(paste0("lavaan:", lab),
    pe$est[pe$label == lab])
"""


@unittest.skipUnless(_has_lavaan(), "R (Rscript) with the lavaan package is not installed")
class RCrossCheckTests(unittest.TestCase):
    def test_paths_bootstrap_and_lavaan_agree_with_r(self):
        frame = synthetic()                 # complete: one data file serves every R model
        spec4 = ProcessSpec("4", "x", "y", ("m1", "m2"), covariates=("age", "employed"),
                            resamples=1000)
        result = fit_process(frame, spec4)
        self.assertEqual(len(complete(frame, spec4)), len(frame))
        spec1 = ProcessSpec("1", "x", "y", w="w", covariates=("age", "employed"))
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            frame.to_csv(folder / "d.csv", index=False)
            np.savetxt(folder / "idx.csv", result.indices, fmt="%d", delimiter=",")
            script = folder / "check.R"
            script.write_text(R_SCRIPT, encoding="utf-8")
            values = self.run_r(script, folder / "d.csv", folder / "idx.csv")
        values1 = values
        y_eq = result.equation("y")
        names = ["(Intercept)", "x", "m1", "m2", "age", "employed"]
        for coefficient, name in zip(y_eq.coefficients, names):
            self.assertClose(coefficient.b, values[f"y:{name}"], 1e-8, name)
            self.assertClose(coefficient.se, values[f"y_se:{name}"], 1e-8, name)
        self.assertClose(result.estimate("a:m0").value, values["a1"], 1e-8, "a1")
        self.assertClose(result.estimate("a:m0").se, values["a1_se"], 1e-8, "a1 se")
        self.assertClose(result.estimate("a:m1").value, values["a2"], 1e-8, "a2")
        self.assertClose(result.estimate("total").value, values["total"], 1e-8, "total")
        for j, label in ((0, "1"), (1, "2")):
            estimate = result.estimate(f"indirect:m{j}")
            self.assertClose(estimate.ci_low, values[f"ci{label}_low"], 1e-8, f"ci{label} low")
            self.assertClose(estimate.ci_high, values[f"ci{label}_high"], 1e-8, f"ci{label} high")
        # lavaan's ML path model: the same coefficients and products.
        for key, name in (("a:m0", "a1"), ("a:m1", "a2"), ("b:m0", "b1"), ("b:m1", "b2"),
                          ("direct", "cp")):
            self.assertClose(result.estimate(key).value, values[f"lavaan:{name}"], 1e-5, name)
        self.assertClose(result.estimate("indirect:m0").value, values["lavaan:ind1"], 1e-5, "ab1")
        self.assertClose(result.estimate("indirect:m1").value, values["lavaan:ind2"], 1e-5, "ab2")
        model1 = fit_process(frame, spec1)
        self.assertClose(model1.estimate("interaction").value, values1["b3"], 1e-8, "b3")
        plus = next(e for e in model1.conditional if e.where == "w.plus")
        self.assertClose(plus.value, values1["theta_plus"], 1e-8, "theta(+1 SD)")
        self.assertClose(plus.se, values1["theta_plus_se"], 1e-8, "se theta(+1 SD)")

    def run_r(self, script, data, indices) -> dict[str, float]:
        done = subprocess.run([RSCRIPT, "--vanilla", str(script), str(data), str(indices)],
                              capture_output=True, text=True, timeout=600)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        values = {}
        for line in done.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2:
                values[parts[0]] = float(parts[1])
        return values

    def assertClose(self, actual, expected, rel, msg):
        self.assertTrue(math.isclose(float(actual), float(expected), rel_tol=rel, abs_tol=1e-12),
                        f"{msg}: {actual!r} != {expected!r}")


if __name__ == "__main__":
    unittest.main()
