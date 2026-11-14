"""RealSampleCalibration for an agent: the stage constants from one reference feature of a real sample, step by step.

The same fit as the RealSampleCalibration window (`quickalignment.realsample.fit`):

1. `start`: what was recalibrated (mode "optics": the focusing optic was realigned, the usual case; "full":
   optics + motors, after re-homing / maintenance / first use), the optic, the plate, the reference feature
   (plate x, y and its height H above the plate surface).
2. `measure_set` for every set of the protocol (`guide` says how to measure it and where the newest
   configuration expects the feature).
3. `fit`: constants, uncertainties, residuals, change from the newest configuration; a round of test points
   at other rotations is predicted.
4. `answer_test` for each test point (found at the prediction, or the real ST, SZ, optic), then `fit` again,
   until every test point of a round is found.
5. `save`: a new configuration in configs/ (QuickAlignment loads it at its next start with that optic).
"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from ..core.calibration import CalibrationStore
from ..core.geometry import PLATES, SN_REFERENCE_W
from ..core.motors import out_of_range
from ..core.schematic import feature_warnings
from ..core.stage import MotorPositions, StageModel
from ..realsample.fit import (
    FIT_PARAMS, FOUND_TOLERANCE, OPTIC_PARAM, PARAM_LABELS, MeasurementSet, NotEnoughData, TestPoint,
    fit_real_sample_calibration, on_beam, optic_focus_of, predict_test_point, protocol_sets, real_sample_record,
    verification_angles,
)
from .common import APIError, number, optic_short, optic_type, rounded

RMS_WARNING = 0.02  # mm, as in the window

HOW_TO_MEASURE = {
    "full": ("Set SRn and SRz to the values of the set, PIX = PIY = 150 µm. Set 1 (and any set with sn_kept false): "
             "bring the feature onto the beam with ST / SZ (scan across it, take the centre of the edge / feature), "
             "bring it to the analyzer focus with SN; repeat until both are stable. Sets with sn_kept true: LEAVE SN "
             "AS IN SET 1, bring the feature onto the beam with ST / SZ and refocus the optic. Write down ST, SZ, SN "
             "and the optic position at best focus in every set (needed in the SN-kept sets). After each set the "
             "expected positions of the other sets are recomputed from what was measured (expected_from)."),
    "optics": ("Set SRn and SRz to the values of the set, PIX = PIY = 150 µm. LEAVE SN AS IT IS. Bring the feature "
               "onto the beam with ST / SZ, refocus the optic. Write down ST, SZ, SN and the optic position."),
}


class RealSampleCalibrationSession:
    def __init__(self, configs: str | Path | None = None):
        self.store = CalibrationStore(configs)
        self.mode = None
        self.optic = None
        self.plate = PLATES["standard"]
        self.uvw = (0.0, 0.0, 5.0)
        self.sets: list[MeasurementSet] = []
        self.tests: list[TestPoint] = []
        self.result = None
        self.saved = None
        self.measured: set[str] = set()  # names of the sets with entered values
        self.sn_kept = True  # full mode: rotated sets measured with SN as in set 1 and the optic refocused
        self.last_fit = None  # the newest fit, kept for the expected positions when sets change afterwards

    # --------------------------------------------------------------------------------------------- setup
    def start(self, mode: str = "optics", optic: str | None = None, plate: str = "standard",
              feature_x: float = 0.0, feature_y: float = 0.0, feature_height: float = 0.0,
              sn_kept: bool = True) -> dict:
        """Begin a calibration: mode "optics" (optic realigned: ST0, SZ0, optic reference; the mechanics are kept
        from the newest configuration) or "full" (optics + motors: all constants), the optic, the plate and the
        reference feature (plate x, y in mm and its height H above the plate surface). `sn_kept` (full mode): the
        rotated sets keep the SN of set 1 and refocus the optic (usual); false: every set is moved to the analyzer
        focus with SN."""
        mode = str(mode).strip().lower()
        mode = "optics" if mode.startswith("opt") else "full" if mode in ("full", "all", "motors", "optics + motors") \
            else mode
        if mode not in ("optics", "full"):
            raise APIError("mode: 'optics' (only the focusing optic was realigned) or 'full' (optics + motors).")
        self.optic = optic_type(optic)
        key = str(plate).strip().lower()
        key = "gating" if key.startswith("gat") else "standard" if key.startswith("st") else key
        if key not in PLATES:
            raise APIError("plate: 'standard' or 'gating' (a custom plate cannot be used for the calibration).")
        prev = self.store.latest(self.optic)
        if mode == "optics" and (prev.path is None or prev.optic_name != optic_short(self.optic)):
            raise APIError(f"There is no {optic_short(self.optic)} configuration to keep the mechanics from: use "
                           "mode 'full' (optics + motors).")
        self.mode, self.plate = mode, PLATES[key]
        x, y, h = number(feature_x, "x"), number(feature_y, "y"), number(feature_height, "H")
        self.uvw = (x, y, self.plate.total_thickness + h)
        self.sn_kept = mode == "full" and bool(sn_kept)
        self.sets = protocol_sets(prev.config.srn_ref, mode, sn_kept=self.sn_kept)
        self.tests, self.result, self.saved, self.measured, self.last_fit = [], None, None, set(), None
        out = {"mode": mode, "optic": self.optic, "plate": self.plate.name, "feature": {"x": x, "y": y, "H": h},
               "sn_kept": self.sn_kept,
               "feature_warnings": feature_warnings(self.plate, x, y),
               "previous_configuration": prev.label,
               "kept_from_previous": ([PARAM_LABELS[p] for p in FIT_PARAMS if p not in ("st0", "sz0")]
                                      if mode == "optics" else []),
               "sets": self.sets_table()}
        out.update(self.guide())
        return out

    def _need_start(self) -> None:
        if self.mode is None:
            raise APIError("Call start(mode, optic, plate, feature_x, feature_y, feature_height) first.")

    def previous(self):
        return self.store.latest(self.optic)

    def _reference_set(self) -> MeasurementSet | None:
        """The measured set 1 (SRn = ref, SRz = 0), if any."""
        prev = self.previous()
        for s in self.sets:
            if s.use and self._measured(s) and abs(s.srn - prev.config.srn_ref) < 1e-9 and abs(s.srz) < 1e-9:
                return s
        return None

    def _expectation(self):
        """(model, optic focus, source) giving the expected positions: the fit if there is one, else the newest
        configuration moved onto the measured set 1 (ST0, SZ0, SN_f and the optic from it, mechanics kept), else
        the newest configuration."""
        prev = self.previous()
        focus = optic_focus_of(prev, self.plate) if prev.optic_name == optic_short(self.optic) else None
        fitted = self.result or self.last_fit  # the last fit stays the best guess after a set is added / changed
        if fitted is not None:
            return StageModel(fitted.config, self.plate), fitted.optic_focus, "fit"
        ref = self._reference_set()
        if ref is not None:
            kept = self.mode == "optics" or ref.sn_kept
            try:
                res = fit_real_sample_calibration([ref], self.plate, self.uvw, base=prev.config, mode=self.mode,
                                                  params=("st0", "sz0") if kept else ("st0", "sz0", "sn_f"))
                return (StageModel(res.config, self.plate), focus if res.optic_focus is None else res.optic_focus,
                        f"set {ref.name.split(' ')[0]} measured + newest configuration's rotation axes")
            except (NotEnoughData, np.linalg.LinAlgError, ValueError):
                pass
        return StageModel(prev.config, self.plate), focus, "newest configuration"

    def _kept_sn(self, model: StageModel) -> float:
        """SN of the SN-kept sets: that of the measured set 1, else the analyzer focus at the reference rotation."""
        ref = self._reference_set()
        return ref.sn if ref is not None else model.config.sn_f + self.uvw[2] - SN_REFERENCE_W

    def sets_table(self) -> list[dict]:
        """The sets with where the feature is expected (a start for the search): from the newest configuration,
        from set 1 once it is measured, from the fit once there is one."""
        model, focus, source = self._expectation()
        rows = []
        for s in self.sets:
            if self.mode == "optics" or s.sn_kept:
                sn = self._kept_sn(model)
                st, sz, optic = on_beam(model, self.uvw, s.srn, s.srz, sn, s.pix, s.piy, focus)
                expect = {"ST": st, "SZ": sz, "SN": sn, "optic": optic}
            else:
                m = model.motors_for_target(*self.uvw, srn=s.srn, srz=s.srz, pix=s.pix, piy=s.piy)
                expect = {"ST": m.st, "SZ": m.sz, "SN": m.sn, "optic": focus}
            row = {"name": s.name, "SRn": s.srn, "SRz": s.srz,
                   "sn": "kept (as in set 1), refocus the optic" if self.mode == "optics" or s.sn_kept
                   else "to the analyzer focus",
                   "measured": self._measured(s), "use": s.use, "expected": rounded(expect), "expected_from": source}
            if row["measured"]:
                row["entered"] = rounded({"ST": s.st, "SZ": s.sz, "SN": s.sn, "optic": s.optic})
            rows.append(row)
        return rows

    # ------------------------------------------------------------------------------------------- guidance
    def guide(self) -> dict:
        """Where the calibration stands and the next thing to do."""
        if self.mode is None:
            return {"step": "start", "do": "Ask: was only the focusing optic realigned (mode 'optics', usual) or were "
                    "the motors re-homed / is this the first use (mode 'full')? Which optic and plate? Which reference "
                    "feature (a small sharp feature near the plate centre, its plate x, y and height H)? Then start()."}
        missing = [s.name for s in self.sets if s.use and not self._measured(s)]
        minimum = 1 if self.mode == "optics" else 3
        done = len([s for s in self.sets if s.use and self._measured(s)])
        if self.saved:
            return {"step": "done", "do": f"Saved {self.saved}. QuickAlignment loads it at its next start with the "
                    f"{optic_short(self.optic)}; check it on a sample of known position (found_here)."}
        if self.result is None:
            if done < minimum:
                return {"step": "measure sets", "do": HOW_TO_MEASURE[self.mode], "sets_to_measure": missing,
                        "minimum_sets": minimum}
            return {"step": "fit", "do": f"{done} set(s) measured" + (f" ({', '.join(missing)} still open: "
                    "recommended as a check)" if missing else "") + ". Call fit()."}
        open_tests = [t.name for t in self._last_round() if not t.answered]
        if open_tests:
            return {"step": "test points", "do": "Go to each test point (SRn, SRz, ST, SZ, SN, optic of test_points). "
                    f"Found on the beam in focus within {FOUND_TOLERANCE:g} mm: answer_test(name, found=true). If "
                    "not: keep SRn, SRz, SN, bring the feature onto the beam with ST / SZ, refocus, and "
                    "answer_test(name, st=..., sz=..., optic=...).", "open": open_tests}
        last = self._last_round()
        if last and all(t.found_within_tolerance for t in last):
            return {"step": "save", "do": f"All test points of round {last[0].round} were found at the predictions. "
                    "Ask the user to confirm, then save(comment)."}
        return {"step": "fit again", "do": "Call fit() to correct the configuration with the measured test points; "
                "a new round of test points follows."}

    def _measured(self, s: MeasurementSet) -> bool:
        return s.name in self.measured

    def _last_round(self) -> list[TestPoint]:
        last = max((t.round for t in self.tests), default=0)
        return [t for t in self.tests if t.round == last]

    # ------------------------------------------------------------------------------------------------- data
    def _set(self, name: str) -> MeasurementSet:
        text = str(name).strip()
        for s in self.sets:
            if s.name == text or s.name.split(" ")[0] == text:
                return s
        raise APIError(f"No set {name!r}; sets: {[s.name for s in self.sets]} (or add_set).")

    def add_set(self, name: str, srn: float, srz: float, sn_kept: bool | None = None) -> dict:
        """Another set at other angles (more redundancy); `sn_kept` default: as the session (start)."""
        self._need_start()
        if any(s.name == name for s in self.sets):
            raise APIError(f"Set {name!r} exists.")
        kept = self.sn_kept if sn_kept is None else bool(sn_kept)
        self.sets.append(MeasurementSet(str(name), number(srn, "SRn"), number(srz, "SRz"),
                                        sn_kept=self.mode == "full" and kept))
        self.result = None
        return {"sets": self.sets_table()}

    def measure_set(self, name: str, st: float, sz: float, sn: float, optic: float | None = None,
                    pix: float = 150.0, piy: float = 150.0, srn: float | None = None, srz: float | None = None,
                    use: bool = True, sn_kept: bool | None = None) -> dict:
        """The values read for a set (the feature on the beam; in mode 'full' at the analyzer focus, or with SN kept
        and the optic refocused when the set is sn_kept). `sn_kept` overrides how this set was measured."""
        self._need_start()
        s = self._set(name)
        kept = s.sn_kept if sn_kept is None else bool(sn_kept)
        if self.mode == "full" and kept and optic is None:
            raise APIError(f"Set {s.name} is measured with SN kept: give the optic position at best focus (it tells "
                           "where the feature is along the beam), or sn_kept=false if SN was moved to the analyzer "
                           "focus.")
        s.st, s.sz, s.sn = number(st, "ST"), number(sz, "SZ"), number(sn, "SN")
        s.optic = None if optic is None else number(optic, "optic")
        s.pix, s.piy = number(pix, "PIX"), number(piy, "PIY")
        if srn is not None:
            s.srn = number(srn, "SRn")
        if srz is not None:
            s.srz = number(srz, "SRz")
        s.use = bool(use)
        s.sn_kept = self.mode == "full" and kept
        self.measured.add(s.name)
        self.result = None
        bad = out_of_range(s.motors())
        out = {"set": s.name, "entered": rounded(asdict(s)), "out_of_range": bad}
        out.update(self.guide())
        return out

    def fit(self) -> dict:
        """Fit the sets and the measured test points; predict a new round of test points."""
        self._need_start()
        sets = [s for s in self.sets if s.use and self._measured(s)]
        prev = self.previous()
        try:
            res = fit_real_sample_calibration(sets, self.plate, self.uvw, base=prev.config, tests=self.tests,
                                              mode=self.mode)
        except NotEnoughData as exc:
            raise APIError(str(exc) + (" One set is enough (SRn 120 / SRz 0)." if self.mode == "optics" else
                                       " The minimum is 3 sets: SRn 120 / SRz 0, one SRn rotation, one SRz rotation.")) \
                from None
        except (np.linalg.LinAlgError, FloatingPointError, ValueError) as exc:
            raise APIError(f"The fit failed ({exc}): check the entered numbers.") from None
        self.result = self.last_fit = res
        prev_focus = optic_focus_of(prev, self.plate) if prev.optic_name == optic_short(self.optic) else None
        constants = []
        for p in res.params:
            value = res.optic_focus if p == OPTIC_PARAM else getattr(res.config, p)
            old = prev_focus if p == OPTIC_PARAM else getattr(prev.config, p)
            constants.append(rounded({"name": PARAM_LABELS[p], "value": value,
                                      "sigma": res.sigma[p] if res.sigma else None, "previous": old,
                                      "change": None if old is None else value - old}))
        warnings = []
        if res.optic_focus is None:
            warnings.append("No optic position entered: the optic reference is not calibrated.")
        if res.rms > RMS_WARNING:
            warnings.append(f"Residuals above {RMS_WARNING} mm: check the entries with the largest residuals"
                            + ("; if they stay, the mechanics have changed: start again with mode 'full'."
                               if self.mode == "optics" else "."))
        if self.mode == "optics" and len(res.sets) == 1 and not res.tests:
            warnings.append("One set: the kept SRn / SRz axes are not checked (sets 2-3 recommended).")
        if self.mode == "full" and res.dof <= 2 and not res.tests:
            warnings.append("Minimum data set: a mistake in a set cannot be seen (sets 4-5 recommended).")
        summary = self._round_summary()
        self._new_round()
        out = {"constants": constants,
               "kept": rounded({PARAM_LABELS[p]: getattr(res.config, p) for p in FIT_PARAMS if p not in res.params}),
               "set_residuals_mm": [rounded({"set": n, "ST": a, "SZ": b, "SN": c, "optic": dict(res.optic_residuals).get(n)})
                                    for n, a, b, c in res.residuals],
               "test_residuals_mm": [rounded({"test": n, "ST": a, "SZ": b, "optic": c}) for n, a, b, c in res.test_residuals],
               "rms_mm": rounded(res.rms, 4), "redundant_equations": res.dof, "warnings": warnings,
               "rounds_so_far": summary, "test_points": self.test_points()["test_points"]}
        out.update(self.guide())
        return out

    def _new_round(self) -> None:
        self.tests = [t for t in self.tests if t.answered]
        n = max((t.round for t in self.tests), default=0) + 1
        model = StageModel(self.result.config, self.plate)
        sn = self._test_sn(model)
        for i, (name, srn, srz) in enumerate(verification_angles(self.result.config.srn_ref), 1):
            t = TestPoint(f"{n}.{i} {name}", srn, srz, round=n)
            self.tests.append(predict_test_point(model, self.uvw, t, self.result.optic_focus, sn=sn))

    def _test_sn(self, model: StageModel) -> float | None:
        """SN of the test points: kept as in set 1 when the sets were measured that way (full mode, SN kept),
        else None (moved to the analyzer focus)."""
        if self.mode == "full" and any(s.sn_kept for s in self.sets if s.use and self._measured(s)):
            return self._kept_sn(model)
        return None

    def _round_summary(self) -> list[str]:
        answered = [t for t in self.tests if t.answered]
        out = []
        for r in sorted({t.round for t in answered}):
            ts = [t for t in answered if t.round == r]
            found = sum(t.found_within_tolerance for t in ts)
            measured = [max(abs(d) for d in t.deviation() if d is not None) for t in ts if t.measured]
            out.append(f"round {r}: {found} of {len(ts)} found within {FOUND_TOLERANCE:g} mm"
                       + (f", largest deviation {max(measured):.4f} mm" if measured else ""))
        return out

    def test_points(self) -> dict:
        """The test points of the open round: where to go (SRn, SRz, ST, SZ, SN, optic)."""
        self._need_start()
        if self.result is None:
            raise APIError("No fit yet: measure the sets and call fit().")
        rows = []
        for t in self._last_round():
            m = MotorPositions(st=t.pred_st, sz=t.pred_sz, sn=t.sn, srn=t.srn, srz=t.srz, pix=t.pix, piy=t.piy)
            row = {"name": t.name, "go_to": rounded({"SRn": t.srn, "SRz": t.srz, "ST": t.pred_st, "SZ": t.pred_sz,
                                                     "SN": t.sn, "optic": t.pred_optic}),
                   "out_of_range": out_of_range(m), "answered": t.answered}
            if t.answered:
                row["deviation_mm"] = rounded(dict(zip(("ST", "SZ", "optic"), t.deviation())))
            rows.append(row)
        return {"round": self._last_round()[0].round if self.tests else 0, "test_points": rows}

    def answer_test(self, name: str, found: bool = False, st: float | None = None, sz: float | None = None,
                    optic: float | None = None) -> dict:
        """A test point: found at the prediction (within 0.05 mm), or the real ST, SZ (and optic) with the feature on
        the beam in focus, SRn / SRz / SN as given."""
        self._need_start()
        t = next((t for t in self._last_round() if t.name == name or t.name.split(" ")[0] == str(name)), None)
        if t is None:
            raise APIError(f"No open test point {name!r}; open: {[t.name for t in self._last_round()]}.")
        if found:
            t.found, t.st, t.sz, t.optic = True, None, None, None
        else:
            if st is None or sz is None:
                raise APIError("Give found=true, or the real st and sz (and optic).")
            t.found, t.st, t.sz = False, number(st, "ST"), number(sz, "SZ")
            t.optic = None if optic is None else number(optic, "optic")
        out = {"test": t.name, "found_within_tolerance": t.found_within_tolerance,
               "deviation_mm": rounded(dict(zip(("ST", "SZ", "optic"), t.deviation())))}
        out.update(self.guide())
        return out

    def change_test_angles(self, name: str, srn: float, srz: float) -> dict:
        """Other angles for an open test point (e.g. out of range), predicted again."""
        t = next((t for t in self._last_round() if t.name == name or t.name.split(" ")[0] == str(name)), None)
        if t is None or self.result is None:
            raise APIError(f"No open test point {name!r}.")
        i = self.tests.index(t)
        model = StageModel(self.result.config, self.plate)
        self.tests[i] = predict_test_point(model, self.uvw, replace(t, srn=number(srn, "SRn"), srz=number(srz, "SRz")),
                                           self.result.optic_focus, sn=self._test_sn(model))
        return self.test_points()

    def save(self, comment: str = "") -> dict:
        """Save the fitted configuration in configs/ (only after the user agreed)."""
        self._need_start()
        if self.result is None:
            raise APIError("Nothing to save: fit() first.")
        prev = self.previous()
        record = real_sample_record(self.result, self.plate, self.uvw, self.optic, str(comment or "").strip(),
                                    tests=[t for t in self.tests if t.answered], previous=prev.label)
        if prev.optic_name == record.optic_name:
            record = replace(record, collision=prev.collision)
        try:
            saved = self.store.save(record)
        except OSError as exc:
            raise APIError(f"Could not write to {self.store.folder}: {exc}") from None
        self.saved = saved.path.name
        return {"saved": str(saved.path), "comment": saved.comment, **self.guide()}

    def status(self) -> dict:
        if self.mode is None:
            return self.guide()
        return {"mode": self.mode, "optic": self.optic, "plate": self.plate.name,
                "feature": rounded({"x": self.uvw[0], "y": self.uvw[1], "H": self.uvw[2] - self.plate.total_thickness}),
                "sets": self.sets_table(), "fitted": self.result is not None, **self.guide()}


__all__ = ["RealSampleCalibrationSession"]
