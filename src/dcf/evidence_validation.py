"""
evidence_validation.py  —  DCF Version 1.2.0

Stage 8: Evidence Validation and Support Assessment, per DCF specification
Section 18.

Implements frozen evidence-state rules from the DCF v1.2.0 publication specification
Copy (Part 6.4 and Part 7.6) as corrected by the Controlling Addendum
(Section 1 ordered Level 1 sequence; Section 2 Stage-E2 design).

LEVEL 1 — ordered, mutually exclusive decision sequence (Addendum §1):
  Rule 0: insufficient valid dimensions -> level_1_analysis_valid=False,
           level_1_analysis_status='insufficient_dimensions', state=null
  Rule 1a: Inconclusive (first)  — any strong_signal fails
            leave_one_out_sign_stable (LOO override)
  Rule 1b: (reserved)            — predefined contradiction; requires
            separately pre-registered, outcome-independent common
            directional interpretation; none currently registered;
            raw Spearman signs alone do not establish contradiction
  Rule 2: Supported              — >=2 independent strong units (standalone
           or coupled), LOO-stable, no predefined contradiction
  Rule 3: Partially Supported    — >=1 independent strong unit OR >=2
           weak_signal, Supported not met, no predefined contradiction
  Rule 4: Inconclusive (catch-all) — >=1 weak_signal or stronger, none of
           the above rules fired
  Rule 5: Unsupported            — no weak_signal or stronger

  level_1_analysis_valid = (count of well-defined dimensions >= 4).

LEVEL 2 — five-step ordered synthesis (publication specification Copy Part 7.6):
  Step 1: |r| < 0.10            -> Unsupported
  Step 2: r < 0, |r|>=0.10,
          p_mantel<0.05          -> Unsupported, contradictory_direction=True
  Step 3: r>=0.40, p_mantel<0.05 -> Supported (before sensitivity check)
  Step 4: 0.20<=r<0.40,
          p_mantel<0.05          -> Partially Supported
  Step 5: all remaining with
          |r|>=0.10              -> Inconclusive

  Sensitivity downgrade (APPROVED OI-5):
    stability_proportion = (LODO analyses preserving same-or-better state) / 10
    Supported  + stability_proportion < 0.80 -> Partially Supported
    Part. Sup. + stability_proportion < 0.70 -> Inconclusive

  negative_direction = True when r < 0 and |r| >= 0.10.
"""



from __future__ import annotations



import json

from dataclasses import asdict, dataclass

from pathlib import Path

from typing import Optional



from dcf.config import get_config

from dcf.logging_utils import get_execution_logger



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _VALIDATION_ROOT(): return _sub("06_validation")













class MissingGateEvidenceError(Exception):

    """Raised when assess_evidence() is called with gate_summary=None."""











































































































STRUCTURAL_DEPENDENCE_GROUPS: list = [

    {

        "dimensions": ("TSS", "VS"),

        "relationship_type": "shared_decomposition",

        "structural_basis": (

            "TSS and VS share components of the same STL decomposition "

            "(Var(T), Var(S), Var(R) of the same series) and therefore "

            "constitute one structurally dependent evidence unit for synthesis "

            "purposes. This grouping is independent of forecasting outcomes. "

            "Their observed opposite signs in the ten-dataset benchmark are "

            "empirical findings, not structural requirements."

        ),

        "independent_units": 1,

        "expected_sign_pattern": "any",

    },

]





@dataclass

class Level1Assessment:

    level_1_analysis_valid: bool

    level_1_analysis_status: str    

    level_1_evidence_state: Optional[str]  

    n_dimensions_well_defined: int

    n_dimensions_undefined: int

    dimension_findings: list

    rationale: str

    dependence_audit: list = None  





@dataclass

class Level2Assessment:

    level_2_evidence_state: Optional[str]

    negative_direction: bool

    contradictory_direction: bool

    sensitivity_downgrade_applied: bool

    stability_proportion: Optional[float]

    primary_gate_passed: bool

    gate_failure_reason: Optional[str]





@dataclass

class ValidationResult:

    dataset_ids: list

    level_1_assessment: dict

    level_2_assessment: dict

    n_datasets_analyzed: int













def _get_lodo_state(lodo_entry: dict, base_state: str) -> str:

    """Classify the LODO analysis outcome relative to the base state."""

    r = lodo_entry.get("r")

    if r is None:

        return "insufficient"

    

    

    if abs(r) < 0.10:

        return "Unsupported"

    if r < 0:

        return "Unsupported"

    if r >= 0.40:

        return "Supported"

    if r >= 0.20:

        return "Partially Supported"

    return "Inconclusive"





_STATE_RANK = {"Supported": 3, "Partially Supported": 2, "Inconclusive": 1, "Unsupported": 0}





def _same_or_better(lodo_state: str, base_state: str) -> bool:

    return _STATE_RANK.get(lodo_state, -1) >= _STATE_RANK.get(base_state, -1)













def _resolve_dependence_groups(strong: list, groups: list) -> tuple:

    """
    Apply STRUCTURAL_DEPENDENCE_GROUPS to the set of strong_signal findings.

    Returns:
      independent_strong   : list of strong findings NOT in any matched group
      coupled_units        : list of (group_spec, matched_findings, audit_dict)
      dependence_audit     : list of audit dicts for serialization

    Design constraints enforced here:
      - A group is eligible only if BOTH participating dimensions are strong_signal.
      - Eligibility is never inferred from B_i, z_im, rho values, or p-values.
      - A coupled unit carries NO single positive/negative orientation.
      - The group counts as ONE independent evidence unit (no double-counting).
      - Coupling consolidates structurally dependent dimensions into one unit;
        it does not create additional independent evidence.
      - Non-comparable units (coupled + any) count equally toward Supported;
        they are simply not described as same-direction corroboration.
      - No raw-sign comparison is used; contradiction requires a pre-registered
        common directional interpretation (none currently defined).
    """

    by_char = {f["characteristic"]: f for f in strong}

    assigned = set()

    coupled_units = []

    audit = []



    for g in groups:

        d1, d2 = g["dimensions"]

        if d1 not in by_char or d2 not in by_char:

            continue  

        if d1 in assigned or d2 in assigned:

            continue  



        f1, f2 = by_char[d1], by_char[d2]

        r1 = f1.get("spearman_r", 0)

        r2 = f2.get("spearman_r", 0)

        sign1 = 1 if r1 >= 0 else -1

        sign2 = 1 if r2 >= 0 else -1

        signs_opposite = (sign1 != sign2)



        rel_type = g["relationship_type"]

        expected = g["expected_sign_pattern"]

        direction_consistent = (

            True         if expected == "any"

            else signs_opposite if expected == "opposite"

            else (not signs_opposite) if expected == "same"

            else True    

        )



        group_audit = {

            "dimensions": list(g["dimensions"]),

            "relationship_type": rel_type,

            "structural_basis": g["structural_basis"],

            "independent_units": g["independent_units"],

            "expected_sign_pattern": expected,

            "observed_signs_opposite": signs_opposite,

            "direction_consistent_with_authorized_relation": direction_consistent,

            "action": None,  

        }



        if not direction_consistent:

            

            

            group_audit["action"] = (

                "direction_inconsistent_with_authorized_relation"

                " — not shielded; treated as independent contradictory findings"

            )

            audit.append(group_audit)

            continue



        

        

        assigned.add(d1)

        assigned.add(d2)

        group_audit["action"] = (

            "grouped_as_one_independent_evidence_unit_due_to_shared_decomposition"

            " — no scalar orientation; not_directionally_comparable with other units"

        )

        audit.append(group_audit)

        coupled_units.append((g, [f1, f2], group_audit))



    independent_strong = [f for f in strong if f["characteristic"] not in assigned]

    return independent_strong, coupled_units, audit





def _assess_level_1(

    level_1_findings: list,

    gate_summary: dict,

    structural_groups: list = None,

) -> Level1Assessment:

    """
    Dependence-aware Level-1 evidence classification.

    Uses STRUCTURAL_DEPENDENCE_GROUPS (or the supplied structural_groups override
    for testing) to collapse structurally dependent dimensions into one
    independent evidence unit.  Grouping is determined solely from shared
    decomposition structure, independently of any forecasting outcome.

    Standalone-directional scope (current package):
      - Raw Spearman +/- signs alone do NOT establish contradiction between
        different standalone characterization dimensions.
      - No pairwise directional interpretation (e.g. SIS/TDS, SIS/PS, SS/TDS)
        is pre-registered.  None may be invented from observed outcomes.
      - Where no prior common directional interpretation exists, standalone
        units are not_directionally_comparable.
      - not_directionally_comparable units still count independently toward
        the support threshold; they are simply not described as same-direction
        corroboration and cannot trigger contradiction from raw signs alone.
      - A future directional contradiction rule requires a separately
        pre-registered, outcome-independent framework specification.

    Decision table (applied in order after Rule 0 validity gate):

    Case                                                      -> State
    -------------------------------------------------------------------------
    0. < 4 well-defined dimensions                            -> invalid (None)
    1a. LOO-unstable strong finding (any)                     -> Inconclusive
    1b. Predefined contradiction (pre-registered common
        orientation AND conflict) -- none currently
        registered                                            -> (reserved)
    2. >= 2 independent strong units (standalone or coupled),
       LOO-stable, no predefined contradiction                -> Supported
    3. 1 independent strong unit, OR 0 strong + >= 2 weak,
       no predefined contradiction                            -> Partially Supported
    4. 0 strong, 1 weak                                       -> Inconclusive
    5. No signal at or above weak_signal                      -> Unsupported

    Coupling consolidates structurally dependent dimensions into one unit;
    it neither promotes weak findings nor invents directional compatibility.
    Malformed structural metadata falls back to treating all strong findings
    as independent standalone units.
    """

    if structural_groups is None:

        structural_groups = STRUCTURAL_DEPENDENCE_GROUPS



    if not level_1_findings:

        return Level1Assessment(

            level_1_analysis_valid=False,

            level_1_analysis_status="insufficient_dimensions",

            level_1_evidence_state=None,

            n_dimensions_well_defined=0,

            n_dimensions_undefined=0,

            dimension_findings=[],

            rationale="No Level 1 findings available.",

            dependence_audit=[],

        )



    well_defined = [f for f in level_1_findings if f.get("dimension_finding") != "undefined"]

    undefined    = [f for f in level_1_findings if f.get("dimension_finding") == "undefined"]

    n_well_defined = len(well_defined)

    n_undefined    = len(undefined)



    

    if n_well_defined < 4:

        return Level1Assessment(

            level_1_analysis_valid=False,

            level_1_analysis_status="insufficient_dimensions",

            level_1_evidence_state=None,

            n_dimensions_well_defined=n_well_defined,

            n_dimensions_undefined=n_undefined,

            dimension_findings=level_1_findings,

            rationale=f"Only {n_well_defined} well-defined dimensions (need >= 4).",

            dependence_audit=[],

        )



    strong = [f for f in well_defined if f.get("dimension_finding") == "strong_signal"]

    weak   = [f for f in well_defined if f.get("dimension_finding") == "weak_signal"]



    def _sign(f) -> int:

        r = f.get("spearman_r")

        return 1 if (r is not None and r >= 0) else -1



    

    loo_unstable_strong = any(f.get("leave_one_out_sign_stable") is False for f in strong)



    

    try:

        indep_strong, coupled_units, dep_audit = _resolve_dependence_groups(

            strong, structural_groups if structural_groups else []

        )

    except Exception:

        

        indep_strong, coupled_units, dep_audit = strong, [], [

            {"action": "metadata_error_fallback_to_independent_treatment"}

        ]



    

    

    

    

    n_indep_strong_units = len(indep_strong) + len(coupled_units)

    

    

    indep_strong_signs = [_sign(f) for f in indep_strong]



    

    

    

    

    

    



    

    

    

    if loo_unstable_strong:

        state = "Inconclusive"

        rationale = (

            "A strong_signal dimension failed leave_one_out_sign_stable "

            "— overrides support states per Addendum §1."

        )



    

    

    

    

    

    

    

    

    

    



    



    

    

    

    

    

    

    elif n_indep_strong_units >= 2:

        state = "Supported"

        rationale = (

            f"{n_indep_strong_units} independent strong evidence unit(s) "

            f"({len(indep_strong)} standalone, {len(coupled_units)} coupled group(s)); "

            "LOO-stable; no predefined contradiction applies."

        )



    

    elif n_indep_strong_units >= 1 or len(weak) >= 2:

        state = "Partially Supported"

        rationale = (

            f"{n_indep_strong_units} independent strong evidence unit(s) "

            f"and {len(weak)} weak_signal dimension(s); "

            "Supported criterion not met."

        )



    

    elif len(weak) >= 1:

        state = "Inconclusive"

        rationale = (

            f"{len(weak)} weak_signal dimension(s) but no independent strong "

            "evidence unit — neither Supported nor Partially Supported threshold met."

        )



    

    else:

        state = "Unsupported"

        rationale = "No dimension reached weak_signal or stronger."



    return Level1Assessment(

        level_1_analysis_valid=True,

        level_1_analysis_status="complete",

        level_1_evidence_state=state,

        n_dimensions_well_defined=n_well_defined,

        n_dimensions_undefined=n_undefined,

        dimension_findings=level_1_findings,

        rationale=rationale,

        dependence_audit=dep_audit,

    )













def _assess_level_2(level_2_findings: list) -> Level2Assessment:

    """
    Classify Level 2 using the five-step ordered sequence + sensitivity downgrade.
    """

    if not level_2_findings:

        return Level2Assessment(

            level_2_evidence_state=None,

            negative_direction=False,

            contradictory_direction=False,

            sensitivity_downgrade_applied=False,

            stability_proportion=None,

            primary_gate_passed=False,

            gate_failure_reason="No Level 2 findings available.",

        )



    f = level_2_findings[0]



    if f.get("insufficient_datasets"):

        return Level2Assessment(

            level_2_evidence_state="Inconclusive",

            negative_direction=False,

            contradictory_direction=False,

            sensitivity_downgrade_applied=False,

            stability_proportion=None,

            primary_gate_passed=False,

            gate_failure_reason="Insufficient datasets for Level 2 analysis.",

        )



    r       = f.get("spearman_r")

    p       = f.get("p_mantel")

    neg_dir = f.get("negative_direction", False)

    cont    = f.get("contradictory_direction", False)



    if r is None or p is None:

        return Level2Assessment(

            level_2_evidence_state="Inconclusive",

            negative_direction=neg_dir,

            contradictory_direction=cont,

            sensitivity_downgrade_applied=False,

            stability_proportion=None,

            primary_gate_passed=False,

            gate_failure_reason="Spearman r or p_mantel is None.",

        )



    

    abs_r = abs(r)

    if abs_r < 0.10:

        state = "Unsupported"

    elif r < 0 and abs_r >= 0.10 and p < 0.05:

        state = "Unsupported"

    elif r >= 0.40 and p < 0.05:

        state = "Supported"

    elif 0.20 <= r < 0.40 and p < 0.05:

        state = "Partially Supported"

    else:

        state = "Inconclusive"



    

    lodo = f.get("leave_one_out_states", [])

    stability_proportion = None

    downgraded = False



    if state in ("Supported", "Partially Supported") and lodo:

        n_stable = sum(1 for entry in lodo if _same_or_better(_get_lodo_state(entry, state), state))

        n_total  = len(lodo)

        if n_total > 0:

            stability_proportion = n_stable / n_total

            if state == "Supported" and stability_proportion < 0.80:

                state = "Partially Supported"

                downgraded = True

            if state == "Partially Supported" and stability_proportion < 0.70:

                state = "Inconclusive"

                downgraded = True



    negative_direction = (r < 0 and abs_r >= 0.10)



    return Level2Assessment(

        level_2_evidence_state=state,

        negative_direction=negative_direction,

        contradictory_direction=cont,

        sensitivity_downgrade_applied=downgraded,

        stability_proportion=stability_proportion,

        primary_gate_passed=True,

        gate_failure_reason=None,

    )













def assess_evidence(

    relationship_analysis_result: dict,

    *,

    gate_summary,

    config=None,

) -> ValidationResult:

    """
    Stage 8: classify Level 1 and Level 2 evidence.

    gate_summary: mandatory keyword-only; must be a RelativeRepresentationGateSummary
    or dict-form gate summary. Raises MissingGateEvidenceError if None.
    """

    if gate_summary is None:

        raise MissingGateEvidenceError(

            "assess_evidence() requires gate_summary to be provided; "

            "got None. Load and verify the traceability artifact first."

        )



    exec_log = get_execution_logger()

    exec_log.info("[Stage 8] Evidence Validation and Support Assessment")



    dataset_ids      = relationship_analysis_result.get("dataset_ids", [])

    l1_findings      = relationship_analysis_result.get("level_1_findings", [])

    l2_findings      = relationship_analysis_result.get("level_2_findings", [])



    gate_dict = gate_summary if isinstance(gate_summary, dict) else asdict(gate_summary)



    l1_assessment = _assess_level_1(l1_findings, gate_dict)

    l2_assessment = _assess_level_2(l2_findings)



    result = ValidationResult(

        dataset_ids=dataset_ids,

        level_1_assessment=asdict(l1_assessment),

        level_2_assessment=asdict(l2_assessment),

        n_datasets_analyzed=len(dataset_ids),

    )



    _write_validation_result(result)

    return result





def _write_validation_result(result: ValidationResult):

    _VALIDATION_ROOT().mkdir(parents=True, exist_ok=True)

    path = _VALIDATION_ROOT() / "evidence_validation.json"

    with open(path, "w") as f:

        json.dump(asdict(result), f, indent=2, default=str)





def load_validation_result() -> dict:

    path = _VALIDATION_ROOT() / "evidence_validation.json"

    if not path.exists():

        raise FileNotFoundError(f"No validation result found at {path}")

    with open(path) as f:

        return json.load(f)







load_evidence_validation = load_validation_result





EVIDENCE_CLASSES = ("Supported", "Partially Supported", "Inconclusive", "Unsupported")





__all__ = [

    "MissingGateEvidenceError",

    "Level1Assessment",

    "Level2Assessment",

    "ValidationResult",

    "assess_evidence",

    "load_validation_result",

]

