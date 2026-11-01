"""BAM guardrail: validates a proposed beam/power decision and repairs it if needed.

Checks (each returns PASS / FAIL with a detail string for the audit log):
  beam_count    number of lit beams <= K
  power_budget  total power <= Pmax, unlit beams carry 0 W
  power_floor   every lit beam >= p_min
  timing_guard  every cell reaches an SSB slot (and SIB slot) before its max age runs out
  policy_border cells flagged as border cells respect the policy power cap (optional)

The raw DRL output never reaches the network: `repair` always runs, and the audit log
records both the proposed and the final action.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class GuardState:
    ssb_age: np.ndarray   # slots since cell was last lit in an SSB slot
    sib_age: np.ndarray   # slots since cell was last lit in a SIB slot

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
    """Dynamic constraints that can override or supplement default configuration."""
    power_cap: np.ndarray | None = None      # (N,) per-cell power ceiling (W), or None
    forced_lit: np.ndarray | None = None     # (N,) cells that must be lit
    forbidden_lit: np.ndarray | None = None  # (N,) cells that must not be lit
    min_power: np.ndarray | None = None      # (N,) per-cell minimum power (W), or None


@dataclass
class GuardResult:
    lit: np.ndarray
    power: np.ndarray
    checks: dict
    repaired: bool
    notes: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c["status"] == "PASS" for c in self.checks.values())


class BamGuard:
    def __init__(self, cfg: dict):
        s, g = cfg["scenario"], cfg["timing_guard"]
        self.K = int(s["k_beams"])
        self.p_max = float(s["p_max_w"])
        self.p_min = float(s["p_min_w"])
        self.ssb_max = float(g["ssb_max_age_slots"])
        self.sib_max = float(g["sib_max_age_slots"])
        self.border = np.array(g.get("border_cells", []), dtype=int)
        self.border_cap = float(g.get("border_power_cap_w", 0.0))

    # ---- helpers -------------------------------------------------------------
    def _due(self, state: GuardState, ssb: float, sib: float, ssb_period: int = 2, sib_period: int = 8):
        """Cells that must be lit in this slot or they will break their timing deadline."""
        due_ssb = (state.ssb_age + ssb_period > self.ssb_max) if ssb > 0 else np.zeros_like(state.ssb_age, bool)
        due_sib = (state.sib_age + sib_period > self.sib_max) if sib > 0 else np.zeros_like(state.sib_age, bool)
        urgency = np.where(due_ssb | due_sib, np.maximum(state.ssb_age / self.ssb_max, state.sib_age / self.sib_max), 0.0)
        return (due_ssb | due_sib), urgency

    def due_mask(self, state: GuardState, ssb: float, sib: float) -> np.ndarray:
        """Public wrapper around _due. Returns boolean mask of cells that must be lit."""
        due, _ = self._due(state, ssb, sib)
        return due

    def _normalise_power(self, lit: np.ndarray, power: np.ndarray) -> np.ndarray:
        """Enforce the per-beam floor and the Pmax ceiling.

        The proposed TOTAL is preserved when it is <= Pmax (so a controller may deliberately use
        less than Pmax to save energy); it is scaled down only when it exceeds Pmax."""
        n = int(lit.sum())
        if n == 0:
            return np.zeros_like(power, dtype=float)
        p = np.where(lit, np.maximum(power, 0.0), 0.0)
        if p.sum() <= 0:
            p = np.where(lit, self.p_max / n, 0.0)
        floor = min(self.p_min, self.p_max / n)
        target = max(min(self.p_max, float(p.sum())), floor * n)
        extra = np.where(lit, np.maximum(p - floor, 0.0), 0.0)
        budget_left = target - floor * n
        out = np.where(lit, floor, 0.0)
        if extra.sum() > 0:
            out = out + extra / extra.sum() * budget_left
        else:
            out = out + np.where(lit, budget_left / n, 0.0)
        return out

    # ---- public --------------------------------------------------------------
    def check(self, lit, power, state: GuardState, ssb: float, sib: float) -> dict:
        lit = np.asarray(lit, bool)
        power = np.asarray(power, float)
        due, _ = self._due(state, ssb, sib)
        missed = np.where(due & ~lit)[0]
        checks = {
            "beam_count": _res(lit.sum() <= self.K, f"{int(lit.sum())} lit, K={self.K}"),
            "power_budget": _res(power.sum() <= self.p_max + 1e-6 and not (power[~lit] > 1e-9).any(),
                                 f"sum={power.sum():.1f} W, Pmax={self.p_max:.0f} W"),
            "power_floor": _res(not (lit & (power < self.p_min - 1e-9)).any(), f"floor={self.p_min:.1f} W"),
            "timing_guard": _res(len(missed) == 0,
                                 "all due cells lit" if len(missed) == 0 else f"cells {missed.tolist()} would miss SSB/SIB deadline"),
        }
        if len(self.border) and self.border_cap > 0:
            bad = [int(c) for c in self.border if lit[c] and power[c] > self.border_cap + 1e-9]
            checks["policy_border"] = _res(not bad, f"border cells {bad} exceed {self.border_cap:.0f} W cap" if bad else "within cap")
        return checks

    def repair(self, lit, power, state: GuardState, ssb: float, sib: float, priority: np.ndarray | None = None, constraints: Constraints | None = None) -> GuardResult:
        """Return a compliant action. `priority` ranks cells (higher = keep) when beams must be dropped.
        
        `constraints` can provide dynamic power caps, forced/forbidden lit status, and per-cell minimums.
        Repair order:
          1. Apply forbidden_lit mask
          2. Merge timing-due cells with constraints.forced_lit, rank by urgency, keep top K
          3. Enforce K by dropping lowest-priority non-forced beams
          4. Apply power floor and total budget
          5. Apply per-cell power caps and redistribute excess
          6. Apply min_power overrides (taken from largest uncapped beam)
        """
        lit = np.asarray(lit, bool).copy()
        power = np.asarray(power, float).copy()
        n = len(lit)
        prio = np.zeros(n) if priority is None else np.asarray(priority, float)
        constraints = constraints or Constraints()
        
        before = self.check(lit, power, state, ssb, sib)
        notes: list[str] = []

        # Step 1: Forbidden cells cannot be lit
        if constraints.forbidden_lit is not None:
            forbidden = np.asarray(constraints.forbidden_lit, bool)
            forced_off = np.where(lit & forbidden)[0]
            if len(forced_off):
                lit[forced_off] = False
                notes.append(f"turned off forbidden cells {forced_off.tolist()}")

        # Step 2: Merge timing-due + constraints.forced_lit; rank by urgency
        due, urgency = self._due(state, ssb, sib)
        must = np.zeros(n, bool)
        must |= due
        if constraints.forced_lit is not None:
            must |= np.asarray(constraints.forced_lit, bool)
        
        forced = np.where(must)[0]
        if len(forced) > self.K:  # cannot honour all; keep the most urgent
            forced = forced[np.argsort(-urgency[forced])][: self.K]
            must = np.zeros(n, bool)
            must[forced] = True
        
        added = np.where(must & ~lit)[0]
        lit |= must
        
        # Step 3: Enforce K by dropping the lowest-priority non-forced beams
        while lit.sum() > self.K:
            cand = np.where(lit & ~must)[0]
            if len(cand) == 0:
                # No non-forced beams to drop; shouldn't happen if must <= K
                break
            drop = cand[np.argmin(prio[cand] + 1e-9 * power[cand])]
            lit[drop] = False
            notes.append(f"dropped cell {int(drop)} (lowest priority) to respect K")
        
        if len(added):
            notes.append(f"forced cells {added.tolist()} on for timing deadline")
        
        # Step 4: Power floor and total budget
        power = np.where(lit, np.where(power > 0, power, power[lit].mean() if lit.any() and (power[lit] > 0).any() else 1.0), 0.0)
        power = self._normalise_power(lit, power)
        
        # Step 5: Apply per-cell power caps and redistribute excess
        if constraints.power_cap is not None:
            cap_array = np.asarray(constraints.power_cap, float)
            capped = np.where(lit & (power > cap_array + 1e-9))[0]
            if len(capped):
                excess = sum(power[c] - cap_array[c] for c in capped)
                for c in capped:
                    power[c] = cap_array[c]
                # Redistribute excess to uncapped lit cells
                uncapped = np.where(lit & (power < cap_array - 1e-9))[0]
                if len(uncapped):
                    power[uncapped] += excess / len(uncapped)
                    # Ensure we don't exceed caps
                    power = np.minimum(power, np.where(lit, cap_array, np.inf))
                notes.append(f"capped cells {capped.tolist()} to per-cell limits (excess redistributed)")
        
        # Also apply legacy border cell cap for backward compatibility
        if len(self.border) and self.border_cap > 0:
            legacy_capped = [int(c) for c in self.border if lit[c] and power[c] > self.border_cap + 1e-9]
            if legacy_capped:
                excess = sum(power[c] - self.border_cap for c in legacy_capped)
                for c in legacy_capped:
                    power[c] = self.border_cap
                others = np.where(lit & ~np.isin(np.arange(n), self.border))[0]
                if len(others):
                    power[others] += excess / len(others)
                notes.append(f"clipped border cells {legacy_capped} to {self.border_cap:.0f} W (policy cap)")
        
        # Step 6: Apply per-cell min_power overrides (taken from largest uncapped beam)
        if constraints.min_power is not None:
            min_pwr = np.asarray(constraints.min_power, float)
            under = np.where(lit & (power < min_pwr))[0]
            if len(under):
                deficit = sum(min_pwr[c] - power[c] for c in under)
                # Take from largest lit beam that's not being forced to minimum
                candidates = np.where(lit & ~np.isin(np.arange(n), under))[0]
                if len(candidates):
                    max_idx = candidates[np.argmax(power[candidates])]
                    power[max_idx] -= deficit
                    for c in under:
                        power[c] = min_pwr[c]
                    notes.append(f"applied min_power constraints on cells {under.tolist()}")
        
        after = self.check(lit, power, state, ssb, sib)
        repaired = (not all(c["status"] == "PASS" for c in before.values())) or bool(notes)
        return GuardResult(lit, power, after, repaired, notes)


def _res(ok: bool, detail: str) -> dict:
    return {"status": "PASS" if ok else "FAIL", "detail": detail}
