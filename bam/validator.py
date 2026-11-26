"""BAM guardrail: validate and repair beam and power proposals before execution."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class GuardState:
    ssb_age: np.ndarray
    sib_age: np.ndarray

    @classmethod
    def fresh(cls, n: int) -> "GuardState":
        return cls(np.zeros(n), np.zeros(n))

    def copy(self) -> "GuardState":
        return GuardState(self.ssb_age.copy(), self.sib_age.copy())

    def advance(self, lit: np.ndarray, ssb: float, sib: float) -> None:
        self.ssb_age = np.where(lit & (ssb > 0), 0.0, self.ssb_age + 1)
        self.sib_age = np.where(lit & (sib > 0), 0.0, self.sib_age + 1)


@dataclass
class Constraints:
    """Dynamic constraints that supplement the static beam and power limits."""
    power_cap: np.ndarray | None = None
    forced_lit: np.ndarray | None = None
    forbidden_lit: np.ndarray | None = None
    min_power: np.ndarray | None = None
    protected_lit: np.ndarray | None = None


class InfeasibleConstraintsError(ValueError):
    """Raised when hard beam or power requirements cannot be satisfied together."""


@dataclass
class GuardResult:
    lit: np.ndarray
    power: np.ndarray
    checks: dict
    repaired: bool
    notes: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check["status"] == "PASS" for check in self.checks.values())


class BamGuard:
    def __init__(self, cfg: dict):
        scenario, timing = cfg["scenario"], cfg["timing_guard"]
        self.K = int(scenario["k_beams"])
        self.p_max = float(scenario["p_max_w"])
        self.p_min = float(scenario["p_min_w"])
        self.ssb_max = float(timing["ssb_max_age_slots"])
        self.sib_max = float(timing["sib_max_age_slots"])
        self.border = np.asarray(timing.get("border_cells", []), dtype=int)
        self.border_cap = float(timing.get("border_power_cap_w", 0.0))
        if self.K < 1 or self.p_max <= 0 or self.p_min < 0:
            raise ValueError("beam count and power limits must be positive")
        if self.ssb_max <= 0 or self.sib_max <= 0:
            raise ValueError("SSB/SIB maximum ages must be positive")
        if self.border.ndim != 1 or (self.border < 0).any() or (self.border >= int(scenario["n_cells"])).any():
            raise ValueError("border_cells must contain valid cell indices")
        if self.border_cap < 0:
            raise ValueError("border_power_cap_w must be non-negative")

    def _due(self, state: GuardState, ssb: float, sib: float, ssb_period: int = 2,
             sib_period: int = 8, protected: np.ndarray | None = None):
        """Select cells for early signalling service, reserving slots to drain a full backlog."""
        n = len(state.ssb_age)
        protected_count = int(np.asarray(protected, bool).sum()) if protected is not None else 0
        service_beams = max(self.K - protected_count, 1)
        reserve_ssb = int(np.ceil(n / service_beams)) * ssb_period
        reserve_sib = int(np.ceil(n / service_beams)) * sib_period
        threshold_ssb = max(0.0, self.ssb_max - reserve_ssb)
        threshold_sib = max(0.0, self.sib_max - reserve_sib)
        due_ssb = (state.ssb_age + ssb_period > threshold_ssb) if ssb > 0 else np.zeros(n, bool)
        due_sib = (state.sib_age + sib_period > threshold_sib) if sib > 0 else np.zeros(n, bool)
        candidates = due_ssb | due_sib
        urgency = np.maximum(state.ssb_age / self.ssb_max, state.sib_age / self.sib_max)
        indexes = np.flatnonzero(candidates)
        if len(indexes) > self.K:
            selected = indexes[np.argsort(-urgency[indexes], kind="stable")[: self.K]]
            candidates = np.zeros(n, dtype=bool)
            candidates[selected] = True
        return candidates, urgency

    def _expired(self, state: GuardState, ssb: float, sib: float,
                 ssb_period: int = 2, sib_period: int = 8) -> np.ndarray:
        expired_ssb = (state.ssb_age + ssb_period > self.ssb_max) if ssb > 0 else np.zeros_like(state.ssb_age, bool)
        expired_sib = (state.sib_age + sib_period > self.sib_max) if sib > 0 else np.zeros_like(state.sib_age, bool)
        return expired_ssb | expired_sib

    def due_mask(self, state: GuardState, ssb: float, sib: float,
                 protected: np.ndarray | None = None) -> np.ndarray:
        due, _ = self._due(state, ssb, sib, protected=protected)
        return due

    @staticmethod
    def _mask(values, name: str, n: int) -> np.ndarray:
        raw = np.asarray(values)
        if raw.shape != (n,):
            raise ValueError(f"{name} must have shape ({n},)")
        try:
            numeric = raw.astype(float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must contain boolean-compatible values") from exc
        if not np.isfinite(numeric).all():
            raise ValueError(f"{name} must contain only finite values")
        return numeric.astype(bool)

    @staticmethod
    def _values(values, name: str, n: int, *, allow_infinity: bool = False) -> np.ndarray:
        try:
            array = np.asarray(values, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must contain numeric values") from exc
        if array.shape != (n,):
            raise ValueError(f"{name} must have shape ({n},)")
        invalid = np.isnan(array) | (np.isneginf(array) if allow_infinity else ~np.isfinite(array))
        if invalid.any():
            qualifier = "NaN or negative infinity" if allow_infinity else "only finite values"
            raise ValueError(f"{name} must contain {qualifier}")
        return array

    def _validate_inputs(self, lit, power, state: GuardState, priority=None):
        raw_lit = np.asarray(lit)
        if raw_lit.ndim != 1 or len(raw_lit) == 0:
            raise ValueError("lit must be a non-empty one-dimensional array")
        lit_array = self._mask(raw_lit, "lit", len(raw_lit))
        power_array = self._values(power, "power", len(lit_array))
        for name, ages in (("ssb_age", state.ssb_age), ("sib_age", state.sib_age)):
            age_array = self._values(ages, name, len(lit_array))
            if (age_array < 0).any():
                raise ValueError(f"{name} must be non-negative")
        priority_array = np.zeros(len(lit_array)) if priority is None else self._values(
            priority, "priority", len(lit_array)
        )
        return lit_array, power_array, priority_array

    def _constraint_arrays(self, constraints: Constraints, n: int):
        cap = np.full(n, np.inf)
        if constraints.power_cap is not None:
            cap = self._values(constraints.power_cap, "power_cap", n, allow_infinity=True)
            if (cap < 0).any():
                raise ValueError("power_cap must be non-negative")

        minimum = np.zeros(n)
        if constraints.min_power is not None:
            minimum = self._values(constraints.min_power, "min_power", n)
            if (minimum < 0).any():
                raise ValueError("min_power must be non-negative")

        forced = np.zeros(n, dtype=bool) if constraints.forced_lit is None else self._mask(
            constraints.forced_lit, "forced_lit", n
        )
        forbidden = np.zeros(n, dtype=bool) if constraints.forbidden_lit is None else self._mask(
            constraints.forbidden_lit, "forbidden_lit", n
        )
        protected = np.zeros(n, dtype=bool) if constraints.protected_lit is None else self._mask(
            constraints.protected_lit, "protected_lit", n
        )
        return cap, minimum, forced, forbidden, protected

    def check(self, lit, power, state: GuardState, ssb: float, sib: float,
              constraints: Constraints | None = None) -> dict:
        lit, power, _ = self._validate_inputs(lit, power, state)
        constraints = constraints or Constraints()
        cap, minimum, forced, forbidden, _ = self._constraint_arrays(constraints, len(lit))
        expired = self._expired(state, ssb, sib)
        missed = np.where(expired & ~lit)[0]
        required_off = np.where((expired | forced) & ~lit)[0]
        forbidden_on = np.where(forbidden & lit)[0]
        over_cap = np.where(lit & (power > cap + 1e-9))[0]
        below_minimum = np.where(lit & (power < minimum - 1e-9))[0]
        checks = {
            "beam_count": _res(lit.sum() <= self.K, f"{int(lit.sum())} lit, K={self.K}"),
            "power_budget": _res(
                (power >= -1e-9).all()
                and power.sum() <= self.p_max + 1e-6
                and not (np.abs(power[~lit]) > 1e-9).any(),
                f"sum={power.sum():.1f} W, Pmax={self.p_max:.0f} W",
            ),
            "power_floor": _res(
                not (lit & (power < self.p_min - 1e-9)).any(),
                f"floor={self.p_min:.1f} W",
            ),
            "timing_guard": _res(
                len(missed) == 0,
                "all due cells lit" if len(missed) == 0 else f"cells {missed.tolist()} would miss SSB/SIB deadline",
            ),
            "dynamic_power_cap": _res(
                len(over_cap) == 0,
                "within dynamic power caps" if len(over_cap) == 0 else f"cells {over_cap.tolist()} exceed dynamic power caps",
            ),
            "dynamic_min_power": _res(
                len(below_minimum) == 0,
                "within dynamic minimum powers" if len(below_minimum) == 0 else f"cells {below_minimum.tolist()} are below dynamic minimum power",
            ),
            "forced_lit": _res(
                len(required_off) == 0,
                "all required cells lit" if len(required_off) == 0 else f"required cells {required_off.tolist()} are dark",
            ),
            "forbidden_lit": _res(
                len(forbidden_on) == 0,
                "all forbidden cells dark" if len(forbidden_on) == 0 else f"forbidden cells {forbidden_on.tolist()} are lit",
            ),
        }
        if len(self.border) and self.border_cap > 0:
            bad = [int(c) for c in self.border if lit[c] and power[c] > self.border_cap + 1e-9]
            checks["policy_border"] = _res(
                not bad,
                f"border cells {bad} exceed {self.border_cap:.0f} W cap" if bad else "within cap",
            )
        return checks

    def repair(self, lit, power, state: GuardState, ssb: float, sib: float,
               priority: np.ndarray | None = None, constraints: Constraints | None = None) -> GuardResult:
        """Repair a proposal or reject mutually infeasible hard constraints."""
        lit, power, priority = self._validate_inputs(lit, power, state, priority)
        n = len(lit)
        constraints = constraints or Constraints()
        cap, minimum, forced, forbidden, protected = self._constraint_arrays(constraints, n)
        before = self.check(lit, power, state, ssb, sib, constraints)
        due, urgency = self._due(state, ssb, sib, protected=protected)
        expired = self._expired(state, ssb, sib)
        mandatory = expired | forced

        conflicts = np.where(mandatory & forbidden)[0]
        if len(conflicts):
            raise InfeasibleConstraintsError(
                f"cells {conflicts.tolist()} are both required and forbidden"
            )
        if int(mandatory.sum()) > self.K:
            raise InfeasibleConstraintsError(
                f"{int(mandatory.sum())} cells are past deadline or forced but the beam limit is {self.K}"
            )

        notes: list[str] = []
        forbidden_removed = np.where(lit & forbidden)[0]
        lit = lit & ~forbidden
        protected_selected = lit & protected & ~mandatory
        protected_cells = np.flatnonzero(protected_selected)
        protected_slots = max(self.K - int(mandatory.sum()), 0)
        if len(protected_cells) > protected_slots:
            keep = protected_cells[np.argsort(-priority[protected_cells], kind="stable")[:protected_slots]]
            protected_selected[:] = False
            protected_selected[keep] = True

        candidates = np.flatnonzero(due & ~mandatory & ~forbidden)
        slots_left = max(self.K - int(mandatory.sum()) - int(protected_selected.sum()), 0)
        if len(candidates) > slots_left:
            candidates = candidates[np.argsort(-urgency[candidates], kind="stable")[:slots_left]]
        proactive = np.zeros(n, dtype=bool)
        proactive[candidates] = True
        required = mandatory | proactive
        must_keep = required | protected_selected

        if len(forbidden_removed):
            notes.append(f"removed forbidden cells {forbidden_removed.tolist()}")

        added = np.where(required & ~lit)[0]
        lit |= required
        while int(lit.sum()) > self.K:
            candidates = np.where(lit & ~must_keep)[0]
            if not len(candidates):
                raise InfeasibleConstraintsError("protected and required beams exceed the beam limit")
            drop = candidates[np.argmin(priority[candidates] + 1e-9 * power[candidates])]
            lit[drop] = False
            notes.append(f"dropped cell {int(drop)} (lowest priority) to respect K")
        if len(added):
            notes.append(f"forced cells {added.tolist()} on for timing or dynamic constraints")

        if len(self.border) and self.border_cap > 0:
            cap[self.border] = np.minimum(cap[self.border], self.border_cap)
        lower = np.maximum(np.full(n, self.p_min), minimum)
        infeasible = np.where(lit & (lower > cap + 1e-9))[0]
        if len(infeasible):
            raise InfeasibleConstraintsError(
                f"power bounds are infeasible for lit cells {infeasible.tolist()}"
            )
        lower_total = float(lower[lit].sum())
        if lower_total > self.p_max + 1e-9:
            raise InfeasibleConstraintsError(
                f"minimum power {lower_total:.3f} W exceeds total budget {self.p_max:.3f} W"
            )

        result_power = np.zeros(n, dtype=float)
        selected = np.where(lit)[0]
        if len(selected):
            proposal = np.maximum(power[selected], 0.0)
            positive = proposal[proposal > 0]
            fallback = float(positive.mean()) if len(positive) else self.p_max / len(selected)
            proposal[proposal == 0] = fallback

            lower_selected, cap_selected = lower[selected], cap[selected]
            target = min(
                self.p_max,
                max(float(proposal.sum()), lower_total),
                float(cap_selected.sum()),
            )
            result_power[selected] = np.clip(proposal, lower_selected, cap_selected)
            difference = target - float(result_power[selected].sum())
            if abs(difference) > 1e-9:
                room = (
                    cap_selected - result_power[selected]
                    if difference > 0
                    else result_power[selected] - lower_selected
                )
                available = room > 1e-12
                if not available.any():
                    raise InfeasibleConstraintsError("power bounds are infeasible for the selected beams")
                unbounded = available & np.isposinf(room)
                if unbounded.any():
                    result_power[selected[unbounded]] += difference / int(unbounded.sum())
                else:
                    adjustment = min(abs(difference), float(room[available].sum()))
                    result_power[selected[available]] += np.sign(difference) * (
                        room[available] * adjustment / float(room[available].sum())
                    )
            if not np.isclose(result_power[selected].sum(), target, rtol=0.0, atol=1e-7):
                raise InfeasibleConstraintsError("power allocation could not satisfy the configured bounds")

        after = self.check(lit, result_power, state, ssb, sib, constraints)
        if not all(check["status"] == "PASS" for check in after.values()):
            failed = [name for name, check in after.items() if check["status"] != "PASS"]
            raise InfeasibleConstraintsError(f"repaired action violates constraints: {failed}")
        repaired = not all(check["status"] == "PASS" for check in before.values()) or bool(notes)
        return GuardResult(lit, result_power, after, repaired, notes)


def _res(ok: bool, detail: str) -> dict:
    return {"status": "PASS" if ok else "FAIL", "detail": detail}
