"""
DCF v1.2.0 — Publication-Evidence Provenance Classification Module
Implements the DCF v1.2.0 publication evidence provenance rule.

Two explicit evidence paths for publication forecasting/evaluation:
  Path A: FRESH_PUBLICATION — executed under this authorization
  Path B: REUSED_VERIFIED — accepted earlier evidence under Section 3 reuse rule

Provenance truthfulness: source runs must NOT be relabelled as publication runs.
"""



import hashlib

import json

import pathlib

from dataclasses import dataclass, field

from typing import Optional



ACCEPTED_FINGERPRINT = 'b64d10258d056fe347ec162484451f46ff14c5e202d8321d1f0740d3c8434f82'



REUSE_ELIGIBLE_DATASETS = {

    'CPIAUCSL', 'Beijing_PM25', 'EUR_USD',

    'Bike_Sharing', 'EIA_Energy_Production', 'FAO_Food_Price',

}



FRESH_EXECUTION_DATASETS = {'INDPRO', 'WTI', 'Jena_Climate', 'SP500'}



PROVENANCE_CLASS_FRESH = 'FRESH_PUBLICATION'

PROVENANCE_CLASS_REUSED = 'REUSED_VERIFIED'





@dataclass

class ReusedVerifiedEvidence:

    """Path B: Accepted earlier corrected-v1.2.0 forecasting/evaluation evidence."""

    dataset_id: str

    final_prepared_sha256: str

    source_experiment_id: str

    source_archive: str

    source_archive_sha256: str

    source_run_type: str        

    source_analysis_role: str   

    implementation_fingerprint: str

    n_origins_authoritative: int

    all_12_models_complete: bool

    evaluation_accounting_pass: bool

    rmse_authority_pass: bool

    naive_denominator_pass: bool

    provenance_reconstructible: bool

    compatibility_basis: str

    provenance_class: str = PROVENANCE_CLASS_REUSED



    def is_eligible(self) -> bool:

        return all([

            self.all_12_models_complete,

            self.evaluation_accounting_pass,

            self.rmse_authority_pass,

            self.naive_denominator_pass,

            self.provenance_reconstructible,

            self.implementation_fingerprint == ACCEPTED_FINGERPRINT,

            self.provenance_class == PROVENANCE_CLASS_REUSED,

            self.source_run_type != 'publication',  

        ])



    def eligibility_status(self) -> str:

        if self.dataset_id not in REUSE_ELIGIBLE_DATASETS:

            return f'INELIGIBLE: {self.dataset_id} not in authorized reuse set'

        if not self.is_eligible():

            failed = []

            if not self.all_12_models_complete:      failed.append('incomplete_models')

            if not self.evaluation_accounting_pass:  failed.append('evaluation_invalid')

            if not self.rmse_authority_pass:         failed.append('rmse_missing')

            if not self.naive_denominator_pass:      failed.append('naive_denominator_invalid')

            if not self.provenance_reconstructible:  failed.append('provenance_incomplete')

            if self.implementation_fingerprint != ACCEPTED_FINGERPRINT:

                failed.append('fingerprint_mismatch')

            if self.source_run_type == 'publication':

                failed.append('source_falsely_relabelled')

            return f'REUSE_NOT_ESTABLISHED: {", ".join(failed)}'

        return 'PUBLICATION_UPSTREAM_EVIDENCE_ELIGIBLE (Path B: REUSED_VERIFIED)'





@dataclass

class FreshPublicationEvidence:

    """Path A: Forecasting/evaluation physically executed under v1.2.0 authorization."""

    dataset_id: str

    final_prepared_sha256: str

    experiment_id: str

    run_type: str = 'publication_upstream_completion'

    analysis_role: str = 'publication_upstream_evidence'

    implementation_fingerprint: str = ACCEPTED_FINGERPRINT

    n_origins_authoritative: int = 0

    all_12_models_complete: bool = False

    evaluation_accounting_pass: bool = False

    rmse_authority_pass: bool = False

    naive_denominator_pass: bool = False

    provenance_class: str = PROVENANCE_CLASS_FRESH



    def is_eligible(self) -> bool:

        return all([

            self.all_12_models_complete,

            self.evaluation_accounting_pass,

            self.rmse_authority_pass,

            self.naive_denominator_pass,

            self.implementation_fingerprint == ACCEPTED_FINGERPRINT,

            self.provenance_class == PROVENANCE_CLASS_FRESH,

        ])



    def eligibility_status(self) -> str:

        if self.dataset_id not in FRESH_EXECUTION_DATASETS:

            return f'INELIGIBLE: {self.dataset_id} not in authorized fresh-execution set'

        if not self.is_eligible():

            failed = []

            if not self.all_12_models_complete:      failed.append('incomplete_models')

            if not self.evaluation_accounting_pass:  failed.append('evaluation_invalid')

            if not self.rmse_authority_pass:         failed.append('rmse_missing')

            if not self.naive_denominator_pass:      failed.append('naive_denominator_invalid')

            if self.implementation_fingerprint != ACCEPTED_FINGERPRINT:

                failed.append('fingerprint_mismatch')

            return f'NOT_COMPLETE: {", ".join(failed)}'

        return 'PUBLICATION_UPSTREAM_EVIDENCE_ELIGIBLE (Path A: FRESH_PUBLICATION)'





def verify_no_generic_bypass(dataset_id: str, provenance_class: str,

                              checkpoint_dir: pathlib.Path) -> bool:

    """
    Adversarial guard: reject any attempt to admit evidence without
    full verification chain. Returns True only if:
    - dataset_id is in the authorized set for that path
    - checkpoint_dir exists and contains at least 12 checkpoint files
    - provenance_class is one of the two authorized strings
    No generic bypass, no name-only reuse.
    """

    authorized_classes = {PROVENANCE_CLASS_FRESH, PROVENANCE_CLASS_REUSED}

    if provenance_class not in authorized_classes:

        return False

    if provenance_class == PROVENANCE_CLASS_REUSED and dataset_id not in REUSE_ELIGIBLE_DATASETS:

        return False

    if provenance_class == PROVENANCE_CLASS_FRESH and dataset_id not in FRESH_EXECUTION_DATASETS:

        return False

    if not checkpoint_dir.exists():

        return False

    n_checkpoints = len(list(checkpoint_dir.glob('*.json')))

    if n_checkpoints < 12:

        return False

    return True

