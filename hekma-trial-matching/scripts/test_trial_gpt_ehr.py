"""Unit tests for trial_gpt_ehr config, eligibility helpers, and profile shaping."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.trial_gpt_ehr_config import TrialGptEhrConfig, clear_trial_gpt_ehr_config_cache
from repositories.trial_gpt_ehr_repo import _profile_for_pipeline
from services.trial_gpt_ehr_eligibility import is_cutoff_eligible
from services.trial_gpt_ehr_ingest_service import (
    TrialGptEhrIngestError,
    TrialGptEhrIngestService,
    is_stale_ingesting_row,
    mark_worker_failure_if_still_ingesting,
)
from services.trial_gpt_ehr_read_service import TrialGptEhrReadService


class TrialGptEhrConfigTests(unittest.TestCase):
    def tearDown(self):
        clear_trial_gpt_ehr_config_cache()

    def test_loads_default_shipped_config(self):
        cfg = TrialGptEhrConfig.load(
            ROOT / "config" / "trial_gpt_ehr_config.json"
        )
        self.assertEqual(cfg.summary_modes, ("llm",))
        self.assertTrue(cfg.p2t_preferred_llm)
        self.assertEqual(cfg.required_llm_flags, frozenset({True}))
        self.assertEqual(
            cfg.fasten_patient_created_at_cutoff,
            datetime(2026, 8, 6, 8, 32, 1, 801000),
        )

    def test_both_modes_allowed(self):
        cfg = TrialGptEhrConfig.from_dict(
            {
                "fastenPatientCreatedAtCutoff": "2026-08-06T08:32:01.801",
                "mysqlPatientCreatedDateCutoff": "2026-08-06",
                "summaryModes": ["llm", "rule_based"],
                "p2tPreferredLlm": True,
            }
        )
        self.assertEqual(cfg.required_llm_flags, frozenset({True, False}))

    def test_rejects_preferred_mode_not_in_summary_modes(self):
        with self.assertRaises(ValueError):
            TrialGptEhrConfig.from_dict(
                {
                    "fastenPatientCreatedAtCutoff": "2026-08-06T08:32:01.801",
                    "summaryModes": ["rule_based"],
                    "p2tPreferredLlm": True,
                }
            )


class CutoffEligibilityTests(unittest.TestCase):
    """Cutoff helper retained for ops; P2T gate no longer uses legacy_skip."""

    def setUp(self):
        self.cfg = TrialGptEhrConfig.from_dict(
            {
                "fastenPatientCreatedAtCutoff": "2026-08-06T08:32:01.801",
                "mysqlPatientCreatedDateCutoff": "2026-08-06",
                "summaryModes": ["llm"],
                "p2tPreferredLlm": True,
            }
        )

    def test_accepts_patient_on_or_after_cutoff(self):
        self.assertTrue(
            is_cutoff_eligible(
                mysql_created_at=date(2026, 8, 6),
                fasten_created_at=datetime(2026, 8, 6, 8, 32, 1, 801000),
                config=self.cfg,
            )
        )

    def test_rejects_fasten_before_cutoff(self):
        self.assertFalse(
            is_cutoff_eligible(
                mysql_created_at=date(2026, 8, 6),
                fasten_created_at=datetime(2026, 8, 6, 8, 0, 0),
                config=self.cfg,
            )
        )

    def test_rejects_mysql_before_cutoff_when_present(self):
        self.assertFalse(
            is_cutoff_eligible(
                mysql_created_at=date(2026, 8, 5),
                fasten_created_at=datetime(2026, 8, 6, 10, 0, 0),
                config=self.cfg,
            )
        )

    def test_allows_missing_mysql_created_when_fasten_ok(self):
        self.assertTrue(
            is_cutoff_eligible(
                mysql_created_at=None,
                fasten_created_at=datetime(2026, 8, 6, 9, 0, 0),
                config=self.cfg,
            )
        )


class ProfilePipelineTests(unittest.TestCase):
    def test_strips_internal_keys_and_flattens_blocks(self):
        profile = _profile_for_pipeline(
            {
                "patient": {"age": "40", "sex": "F"},
                "_generation": {"model": "x"},
                "_icd_diseases": [{"code": "E11"}],
                "note": "ok",
            }
        )
        self.assertEqual(profile["patient"], "age: 40, sex: F")
        self.assertEqual(profile["note"], "ok")
        self.assertNotIn("_generation", profile)
        self.assertNotIn("_icd_diseases", profile)


class IngestServiceAlwaysEhrTests(unittest.TestCase):
    def setUp(self):
        self.cfg = TrialGptEhrConfig.from_dict(
            {
                "fastenPatientCreatedAtCutoff": "2026-08-06T08:32:01.801",
                "summaryModes": ["llm"],
                "p2tPreferredLlm": True,
            }
        )
        self.svc = TrialGptEhrIngestService(config=self.cfg)

    @patch("services.trial_gpt_ehr_ingest_service.trial_gpt_ehr_repo")
    @patch("services.trial_gpt_ehr_ingest_service.get_patient_identity")
    def test_already_present_skips_ingest(self, mock_identity, mock_repo):
        mock_identity.return_value = {
            "mysql_patient_id": 203563,
            "subject_id": "subj-1",
            "created_at": None,
        }
        mock_repo.has_ready_modes.return_value = True
        result = self.svc.ensure_for_p2t("203563")
        self.assertEqual(result.status, "already_present")
        self.assertEqual(result.modes_written, (True,))

    @patch("services.trial_gpt_ehr_ingest_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_ingest_service.trial_gpt_ehr_repo")
    @patch("services.trial_gpt_ehr_ingest_service.get_patient_identity")
    def test_missing_fasten_raises_not_legacy_skip(
        self, mock_identity, mock_repo, mock_fasten
    ):
        mock_identity.return_value = {
            "mysql_patient_id": 203450,
            "subject_id": "subj-legacy",
            "created_at": None,
        }
        mock_repo.has_ready_modes.return_value = False
        mock_fasten.get_fasten_patient_created_at.return_value = None
        mock_fasten.has_clinical_data.return_value = False
        with self.assertRaises(TrialGptEhrIngestError) as ctx:
            self.svc.ensure_for_p2t("203450")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("clinical records", str(ctx.exception))


class DiseaseListRepoTests(unittest.TestCase):
    @patch("repositories.trial_gpt_ehr_repo.pg_transaction")
    def test_fetch_disease_list_returns_names(self, mock_txn):
        from repositories.trial_gpt_ehr_repo import fetch_disease_list

        cur = MagicMock()
        cur.fetchone.return_value = {"disease_list": ["Asthma", "Pneumonia"]}
        mock_txn.return_value.__enter__.return_value = (None, cur)
        out = fetch_disease_list(mysql_patient_id=203563, llm=True)
        self.assertEqual(out, ["Asthma", "Pneumonia"])


class TrialGptEhrReadServiceTests(unittest.TestCase):
    """Background ingest on diseases/summary read when trial_gpt_ehr is missing."""

    def setUp(self):
        self.cfg = TrialGptEhrConfig.from_dict(
            {
                "fastenPatientCreatedAtCutoff": "2026-08-06T08:32:01.801",
                "summaryModes": ["llm"],
                "p2tPreferredLlm": True,
            }
        )

    @patch("services.trial_gpt_ehr_read_service._ensure_schema_once")
    @patch("services.trial_gpt_ehr_read_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_read_service._fetch_icd_entries")
    @patch("services.trial_gpt_ehr_read_service._fetch_disease_list")
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    @patch.object(TrialGptEhrReadService, "schedule_background_ingest")
    def test_prepare_for_read_does_not_schedule_ingest_when_empty(
        self, mock_schedule, mock_repo, mock_fetch, mock_icd, mock_fasten, mock_schema
    ):
        mock_repo.has_ready_modes.return_value = False
        mock_repo.fetch_ehr_status_row.return_value = None
        mock_fetch.return_value = []
        mock_icd.return_value = []
        mock_fasten.get_fasten_patient_created_at.return_value = None
        mock_fasten.has_clinical_data.return_value = False
        mock_fasten.fetch_condition_diseases.return_value = ([], [])

        svc = TrialGptEhrReadService(config=self.cfg)
        prep = svc.prepare_for_read(
            patient_id="203567",
            subject_id="subj-new",
            trigger="diseases",
            sync=False,
        )

        mock_schedule.assert_not_called()
        self.assertEqual(prep["ehr_status"], "preparing")
        self.assertEqual(prep["diseases"], [])

    @patch("services.trial_gpt_ehr_read_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_read_service._fetch_icd_entries")
    @patch("services.trial_gpt_ehr_read_service._fetch_disease_list")
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    @patch.object(TrialGptEhrReadService, "ensure_ready_sync")
    def test_prepare_for_read_sync_waits_for_ingest(
        self, mock_sync, mock_repo, mock_fetch, mock_icd, mock_fasten
    ):
        mock_repo.has_ready_modes.return_value = False
        mock_repo.fetch_ehr_status_row.return_value = None
        mock_fetch.side_effect = [[], ["Type 2 diabetes"]]
        mock_icd.return_value = []
        mock_fasten.fetch_condition_diseases.return_value = ([], [])
        mock_fasten.has_clinical_data.return_value = True
        mock_sync.return_value = MagicMock(status="ingested")

        svc = TrialGptEhrReadService(config=self.cfg)
        with patch.object(svc, "_preflight_fasten"):
            prep = svc.prepare_for_read(
                patient_id="203567",
                subject_id="subj-new",
                trigger="diseases",
                sync=True,
            )

        mock_sync.assert_called_once()
        self.assertEqual(prep["ehr_status"], "ready")
        self.assertEqual(prep["diseases"], ["Type 2 diabetes"])
        self.assertEqual(prep["ingest_result"].status, "ingested")

    @patch("services.trial_gpt_ehr_read_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_read_service._fetch_icd_entries")
    @patch("services.trial_gpt_ehr_read_service._fetch_disease_list")
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    @patch.object(TrialGptEhrReadService, "schedule_background_ingest")
    def test_prepare_for_read_skips_ingest_when_diseases_present(
        self, mock_schedule, mock_repo, mock_fetch, mock_icd, mock_fasten
    ):
        mock_repo.has_ready_modes.return_value = False
        mock_fetch.return_value = ["Asthma"]
        mock_icd.return_value = []
        mock_fasten.fetch_condition_diseases.return_value = ([], [])

        svc = TrialGptEhrReadService(config=self.cfg)
        prep = svc.prepare_for_read(
            patient_id="203563",
            subject_id="subj-1",
            trigger="diseases",
            sync=False,
        )

        mock_schedule.assert_not_called()
        self.assertEqual(prep["ehr_status"], "ready")
        self.assertEqual(prep["diseases"], ["Asthma"])
        self.assertTrue(prep.get("cached"))

    @patch("services.trial_gpt_ehr_read_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_read_service._fetch_icd_entries")
    @patch("services.trial_gpt_ehr_read_service._fetch_disease_list")
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    @patch.object(TrialGptEhrReadService, "schedule_background_ingest")
    def test_cache_hit_skips_ingest_when_ready_row_exists(
        self, mock_schedule, mock_repo, mock_fetch, mock_icd, mock_fasten
    ):
        mock_repo.has_ready_modes.return_value = True
        mock_fetch.return_value = ["Asthma", "Pneumonia"]
        mock_icd.return_value = []
        mock_fasten.fetch_condition_diseases.return_value = ([], [])

        svc = TrialGptEhrReadService(config=self.cfg)
        prep = svc.prepare_for_read(
            patient_id="203578",
            subject_id="subj-1",
            trigger="diseases",
            sync=False,
        )

        mock_schedule.assert_not_called()
        mock_fetch.assert_called_once()
        self.assertEqual(prep["ehr_status"], "ready")
        self.assertEqual(prep["diseases"], ["Asthma", "Pneumonia"])
        self.assertTrue(prep["cached"])

    @patch("services.trial_gpt_ehr_read_service._ensure_schema_once")
    @patch("services.trial_gpt_ehr_read_service.is_stale_ingesting_row", return_value=False)
    @patch("services.trial_gpt_ehr_read_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    def test_get_ehr_status_preparing_when_ingesting(
        self, mock_repo, mock_fasten, mock_stale, mock_schema
    ):
        mock_repo.has_ready_modes.return_value = False
        mock_repo.fetch_ehr_status_row.return_value = {
            "summary_status": "ingesting",
            "updated_at": datetime.utcnow(),
        }
        mock_fasten.has_clinical_data.return_value = True
        mock_fasten.export_fasten_patient_data.return_value = {"fastenhealth_condition": [1, 2]}

        svc = TrialGptEhrReadService(config=self.cfg)
        status = svc.get_ehr_status("203577")

        self.assertEqual(status["ehr_status"], "preparing")
        self.assertEqual(status["stage"], "building_profile")
        self.assertEqual(status["retry_after_seconds"], 15)
        self.assertIn("progress_percent", status)

    @patch("services.trial_gpt_ehr_read_service._ensure_schema_once")
    @patch.object(TrialGptEhrReadService, "schedule_background_ingest")
    @patch("services.trial_gpt_ehr_read_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    @patch("services.trial_gpt_ehr_read_service._fetch_icd_entries")
    @patch("services.trial_gpt_ehr_read_service._fetch_disease_list")
    def test_prepare_for_read_retries_failed_instead_of_503(
        self, mock_fetch, mock_icd, mock_repo, mock_fasten, mock_schedule, mock_schema
    ):
        mock_fetch.return_value = []
        mock_icd.return_value = []
        mock_repo.has_ready_modes.return_value = False
        mock_repo.fetch_ehr_status_row.return_value = {
            "summary_status": "failed",
            "structured_json": {"error": "LLM timeout"},
            "updated_at": datetime.utcnow(),
        }
        mock_fasten.has_clinical_data.return_value = True
        mock_fasten.fetch_condition_diseases.return_value = ([], [])
        mock_fasten.export_fasten_patient_data.return_value = {"fastenhealth_condition": [1]}
        mock_schedule.return_value = True

        svc = TrialGptEhrReadService()
        prep = svc.prepare_for_read(
            patient_id="203578",
            subject_id="subj-1",
            trigger="diseases",
            sync=False,
        )

        self.assertEqual(prep["ehr_status"], "preparing")
        mock_schedule.assert_called_once()
        self.assertTrue(prep["progress"]["retry_scheduled"])

    @patch("services.trial_gpt_ehr_read_service.time.monotonic", return_value=1000.0)
    @patch("services.trial_gpt_ehr_read_service._last_auto_retry_at", {203578: 999.0})
    @patch.object(TrialGptEhrReadService, "schedule_background_ingest")
    @patch("services.trial_gpt_ehr_read_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    def test_auto_retry_respects_cooldown(
        self, mock_repo, mock_fasten, mock_schedule, mock_mono
    ):
        mock_repo.has_ready_modes.return_value = False
        mock_repo.fetch_ehr_status_row.return_value = {"summary_status": "failed"}
        mock_fasten.has_clinical_data.return_value = True
        mock_fasten.export_fasten_patient_data.return_value = {"t": [1]}

        svc = TrialGptEhrReadService()
        scheduled = svc._maybe_auto_retry_ingest(
            patient_id="203578",
            subject_id="subj-1",
            mysql_patient_id=203578,
            summary_row={"summary_status": "failed"},
            trigger="test",
        )
        self.assertFalse(scheduled)
        mock_schedule.assert_not_called()


class IngestServiceInFlightTests(unittest.TestCase):
    @patch("services.trial_gpt_ehr_ingest_service.trial_gpt_ehr_repo")
    @patch("services.trial_gpt_ehr_ingest_service.get_patient_identity")
    def test_ensure_for_p2t_rejects_while_ingesting(self, mock_identity, mock_repo):
        cfg = TrialGptEhrConfig.from_dict(
            {
                "fastenPatientCreatedAtCutoff": "2026-08-06T08:32:01.801",
                "summaryModes": ["llm"],
                "p2tPreferredLlm": True,
            }
        )
        mock_identity.return_value = {
            "mysql_patient_id": 203577,
            "subject_id": "subj-1",
            "created_at": None,
        }
        mock_repo.has_ready_modes.return_value = False
        mock_repo.fetch_ehr_status_row.return_value = {
            "summary_status": "ingesting",
            "updated_at": datetime.utcnow(),
        }

        svc = TrialGptEhrIngestService(config=cfg)
        with self.assertRaises(TrialGptEhrIngestError) as ctx:
            svc.ensure_for_p2t("203577")
        self.assertEqual(ctx.exception.status_code, 409)

    @patch("services.trial_gpt_ehr_ingest_service.TrialGptEhrIngestService._ingest")
    @patch("services.trial_gpt_ehr_ingest_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_ingest_service.trial_gpt_ehr_repo")
    @patch("services.trial_gpt_ehr_ingest_service.get_patient_identity")
    def test_ensure_for_p2t_retries_stale_ingesting(
        self, mock_identity, mock_repo, mock_fasten, mock_ingest
    ):
        cfg = TrialGptEhrConfig.from_dict(
            {
                "fastenPatientCreatedAtCutoff": "2026-08-06T08:32:01.801",
                "summaryModes": ["llm"],
                "p2tPreferredLlm": True,
            }
        )
        mock_identity.return_value = {
            "mysql_patient_id": 203487,
            "subject_id": "subj-1",
            "created_at": None,
        }
        mock_repo.has_ready_modes.return_value = False
        stale_ts = datetime.utcnow().replace(year=2020)
        mock_repo.fetch_ehr_status_row.return_value = {
            "summary_status": "ingesting",
            "updated_at": stale_ts,
        }
        mock_fasten.has_clinical_data.return_value = True
        mock_ingest.return_value = MagicMock(status="ingested")

        svc = TrialGptEhrIngestService(config=cfg)
        result = svc.ensure_for_p2t("203487", skip_inflight_guard=True)

        mock_ingest.assert_called_once()
        self.assertEqual(result.status, "ingested")

    @patch("services.trial_gpt_ehr_ingest_service.TrialGptEhrIngestService._ingest")
    @patch("services.trial_gpt_ehr_ingest_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_ingest_service.trial_gpt_ehr_repo")
    @patch("services.trial_gpt_ehr_ingest_service.get_patient_identity")
    def test_background_worker_skips_inflight_guard(
        self, mock_identity, mock_repo, mock_fasten, mock_ingest
    ):
        """Background thread must not 409 on its own ingesting row."""
        cfg = TrialGptEhrConfig.from_dict(
            {
                "fastenPatientCreatedAtCutoff": "2026-08-06T08:32:01.801",
                "summaryModes": ["llm"],
                "p2tPreferredLlm": True,
            }
        )
        mock_identity.return_value = {
            "mysql_patient_id": 203578,
            "subject_id": "subj-1",
            "created_at": None,
        }
        mock_repo.has_ready_modes.return_value = False
        mock_repo.fetch_ehr_status_row.return_value = {"summary_status": "ingesting"}
        mock_fasten.has_clinical_data.return_value = True
        mock_ingest.return_value = MagicMock(status="ingested")

        svc = TrialGptEhrIngestService(config=cfg)
        result = svc.ensure_for_p2t("203578", skip_inflight_guard=True)

        mock_ingest.assert_called_once()
        self.assertEqual(result.status, "ingested")


class BackgroundIngestFlowTests(unittest.TestCase):
    @patch("services.trial_gpt_ehr_read_service.is_stale_ingesting_row", return_value=False)
    @patch("services.trial_gpt_ehr_read_service.run_background_ingest_with_logging")
    @patch("services.trial_gpt_ehr_read_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    def test_schedule_background_calls_ensure_with_background_trigger(
        self, mock_repo, mock_fasten, mock_run, mock_stale
    ):
        mock_repo.has_ready_modes.return_value = False
        mock_repo.fetch_ehr_status_row.return_value = None
        mock_fasten.has_clinical_data.return_value = True

        svc = TrialGptEhrReadService()
        started = svc.schedule_background_ingest(
            patient_id="203578",
            subject_id="subj-1",
            trigger="diseases",
        )
        self.assertTrue(started)

        import time

        deadline = time.time() + 2.0
        while time.time() < deadline:
            if mock_run.call_count:
                break
            time.sleep(0.05)

        mock_run.assert_called_once_with(
            "203578",
            trigger="background:diseases",
            force=False,
        )

    @patch("services.trial_gpt_ehr_read_service.ensure_trial_gpt_ehr_ready")
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    def test_schedule_background_skips_when_already_ready(
        self, mock_repo, mock_ensure
    ):
        mock_repo.has_ready_modes.return_value = True

        svc = TrialGptEhrReadService()
        started = svc.schedule_background_ingest(
            patient_id="203578",
            subject_id="subj-1",
            trigger="diseases",
        )

        self.assertFalse(started)
        mock_ensure.assert_not_called()

    @patch("services.trial_gpt_ehr_read_service._ensure_schema_once")
    @patch("services.trial_gpt_ehr_read_service.is_stale_ingesting_row", return_value=False)
    @patch("services.trial_gpt_ehr_read_service.fastenhealth_repo")
    @patch.object(TrialGptEhrReadService, "schedule_background_ingest")
    @patch("services.trial_gpt_ehr_read_service._ingest_in_flight", set())
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    @patch("services.trial_gpt_ehr_read_service._fetch_icd_entries")
    @patch("services.trial_gpt_ehr_read_service._fetch_disease_list")
    def test_read_only_returns_preparing_when_ingesting(
        self, mock_fetch, mock_icd, mock_repo, mock_schedule, mock_fasten, mock_stale, mock_schema
    ):
        """Read API returns preparing with progress while ingest runs."""
        mock_fetch.return_value = []
        mock_icd.return_value = []
        mock_repo.has_ready_modes.return_value = False
        mock_repo.fetch_ehr_status_row.return_value = {
            "summary_status": "ingesting",
            "updated_at": datetime.utcnow(),
        }
        mock_fasten.has_clinical_data.return_value = True
        mock_fasten.fetch_condition_diseases.return_value = ([], [])
        mock_fasten.export_fasten_patient_data.return_value = {"fastenhealth_condition": [1]}

        svc = TrialGptEhrReadService()
        prep = svc.prepare_for_read(
            patient_id="203578",
            subject_id="subj-1",
            trigger="diseases",
            sync=False,
        )

        mock_schedule.assert_not_called()
        self.assertEqual(prep["ehr_status"], "preparing")
        self.assertIn("progress", prep)


class TrialGptEhrTriggerServiceTests(unittest.TestCase):
    @patch("services.trial_gpt_ehr_trigger_service.trial_gpt_ehr_repo.ensure_trial_gpt_ehr_table")
    @patch("services.trial_gpt_ehr_trigger_service.is_stale_ingesting_row", return_value=False)
    @patch.object(TrialGptEhrReadService, "schedule_background_ingest")
    @patch.object(TrialGptEhrReadService, "require_fasten_data")
    @patch.object(TrialGptEhrReadService, "has_ready_profile")
    @patch("services.trial_gpt_ehr_trigger_service.get_patient_identity")
    def test_internal_trigger_accepts_new_patient(
        self, mock_identity, mock_ready, mock_fasten, mock_schedule, mock_stale, mock_ensure
    ):
        from services.trial_gpt_ehr_trigger_service import TrialGptEhrTriggerService

        mock_identity.return_value = {
            "mysql_patient_id": 203579,
            "subject_id": "subj-new",
        }
        mock_ready.return_value = False
        mock_schedule.return_value = True

        svc = TrialGptEhrTriggerService()
        result = svc.trigger_ingest("203579", trigger="fasten_ehi_export_success", force=True)

        mock_fasten.assert_called_once()
        mock_schedule.assert_called_once()
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["ehr_status"], "preparing")

    @patch("services.trial_gpt_ehr_trigger_service.trial_gpt_ehr_repo.ensure_trial_gpt_ehr_table")
    @patch("services.trial_gpt_ehr_trigger_service.is_stale_ingesting_row")
    @patch.object(TrialGptEhrReadService, "schedule_background_ingest")
    @patch.object(TrialGptEhrReadService, "require_fasten_data")
    @patch.object(TrialGptEhrReadService, "has_ready_profile")
    @patch("services.trial_gpt_ehr_trigger_service.get_patient_identity")
    def test_internal_trigger_auto_force_when_stale_ingesting(
        self, mock_identity, mock_ready, mock_fasten, mock_schedule, mock_stale, mock_ensure
    ):
        from services.trial_gpt_ehr_trigger_service import TrialGptEhrTriggerService

        mock_identity.return_value = {
            "mysql_patient_id": 203487,
            "subject_id": "subj-stale",
        }
        mock_ready.return_value = False
        mock_stale.return_value = True
        mock_schedule.return_value = True

        svc = TrialGptEhrTriggerService()
        result = svc.trigger_ingest("203487", trigger="fasten_export", force=False)

        mock_schedule.assert_called_once()
        call_kwargs = mock_schedule.call_args.kwargs
        self.assertTrue(call_kwargs["force"])
        self.assertEqual(result["status"], "accepted")


class StaleIngestingRecoveryTests(unittest.TestCase):
    @patch("services.trial_gpt_ehr_ingest_service.trial_gpt_ehr_repo")
    def test_is_stale_ingesting_row_when_old(self, mock_repo):
        mock_repo.fetch_ehr_status_row.return_value = {
            "summary_status": "ingesting",
            "updated_at": datetime.utcnow() - timedelta(seconds=300),
        }
        self.assertTrue(is_stale_ingesting_row(203487, llm=True))

    @patch("services.trial_gpt_ehr_ingest_service.trial_gpt_ehr_repo")
    def test_is_stale_ingesting_row_when_recent(self, mock_repo):
        mock_repo.fetch_ehr_status_row.return_value = {
            "summary_status": "ingesting",
            "updated_at": datetime.utcnow(),
        }
        self.assertFalse(is_stale_ingesting_row(203487, llm=True))

    @patch("services.trial_gpt_ehr_ingest_service.trial_gpt_ehr_repo")
    @patch("services.trial_gpt_ehr_ingest_service.get_patient_identity")
    def test_mark_worker_failure_if_still_ingesting(
        self, mock_identity, mock_repo
    ):
        mock_identity.return_value = {
            "mysql_patient_id": 203487,
            "subject_id": "subj-1",
        }
        mock_repo.fetch_ehr_status_row.return_value = {"summary_status": "ingesting"}

        mark_worker_failure_if_still_ingesting("203487", "worker died")

        mock_repo.mark_failed.assert_called_once()

    @patch("services.trial_gpt_ehr_trigger_service.trial_gpt_ehr_repo.ensure_trial_gpt_ehr_table")
    @patch.object(TrialGptEhrReadService, "schedule_background_ingest")
    @patch.object(TrialGptEhrReadService, "read_diseases_only")
    @patch.object(TrialGptEhrReadService, "has_ready_profile")
    @patch("services.trial_gpt_ehr_trigger_service.get_patient_identity")
    def test_internal_trigger_cache_hit_skips_ingest(
        self, mock_identity, mock_ready, mock_read, mock_schedule, mock_ensure
    ):
        from services.trial_gpt_ehr_trigger_service import TrialGptEhrTriggerService

        mock_identity.return_value = {
            "mysql_patient_id": 203578,
            "subject_id": "subj-1",
        }
        mock_ready.return_value = True
        mock_read.return_value = (["Asthma"], [])

        svc = TrialGptEhrTriggerService()
        result = svc.trigger_ingest("203578", force=False)

        mock_schedule.assert_not_called()
        self.assertEqual(result["status"], "already_present")
        self.assertTrue(result["cached"])


class RuleBasedIcd10DiseaseListTests(unittest.TestCase):
    """No-LLM path keeps only FHIR ICD-10 diagnoses."""

    def test_drops_care_plan_labels_without_icd10(self):
        from services.bundled_hekma.trial_patient_summary import _rule_based_disease_list

        diseases = _rule_based_disease_list(
            {
                "conditions": [
                    {"name": "Asthma", "icd10_code": "J45.909", "clinical_status": "active"},
                    {"name": "Discharge Planning", "clinical_status": "active"},
                    {"name": "Safety Adult - Fall", "clinical_status": "active"},
                    {"name": "Pneumonia", "icd10_code": "J18.9", "clinical_status": "active"},
                ]
            }
        )
        self.assertEqual(diseases, ["Asthma", "Pneumonia"])


class HekmaFastenBridgeTests(unittest.TestCase):
    """Bridge must not crash in Docker where monorepo sibling path is absent."""

    def setUp(self):
        from services import hekma_fasten_bridge

        self.bridge = hekma_fasten_bridge
        self._orig_env = os.environ.get("HEKMA_DATA_PIPELINE_PARENT")
        os.environ["HEKMA_DATA_PIPELINE_PARENT"] = "/nonexistent/hekma/path"

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("HEKMA_DATA_PIPELINE_PARENT", None)
        else:
            os.environ["HEKMA_DATA_PIPELINE_PARENT"] = self._orig_env

    def test_serialize_fasten_rows_uses_bundled_without_sibling_repo(self):
        from datetime import datetime

        export = {
            "fastenhealth_condition": [
                {"id": 1, "patient_id": "203578", "created_at": datetime(2026, 8, 11)}
            ]
        }
        out = self.bridge.serialize_fasten_rows(export)
        self.assertEqual(out["fastenhealth_condition"][0]["created_at"], "2026-08-11T00:00:00")

    def test_get_generate_trial_patient_summary_uses_bundled_without_sibling_repo(self):
        gen = self.bridge.get_generate_trial_patient_summary()
        self.assertEqual(gen.__module__, "services.bundled_hekma.trial_patient_summary")

    def test_find_hekma_parent_returns_none_for_missing_override(self):
        self.assertIsNone(self.bridge._find_hekma_parent())


class FastenConditionDiseaseTests(unittest.TestCase):
    """Diseases from unified fastenhealth_condition (EHR, manual, scan)."""

    def test_extracts_manual_condition_name_from_ctms_payload(self):
        from repositories.fastenhealth_repo import extract_condition_display_name

        resource = {
            "resourceType": "Condition",
            "extension": [
                {
                    "url": "https://hekma.ai/fhir/StructureDefinition/ctms-payload",
                    "valueString": '{"conditionName": "Type 2 diabetes mellitus"}',
                }
            ],
        }
        self.assertEqual(
            extract_condition_display_name(resource),
            "Type 2 diabetes mellitus",
        )

    def test_extracts_ehr_coding_display(self):
        from repositories.fastenhealth_repo import extract_condition_display_name

        resource = {
            "code": {
                "coding": [{"system": "http://snomed.info/sct", "display": "Asthma"}]
            }
        }
        self.assertEqual(extract_condition_display_name(resource), "Asthma")

    @patch("services.trial_gpt_ehr_read_service._ensure_schema_once")
    @patch("services.trial_gpt_ehr_read_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_read_service.trial_gpt_ehr_repo")
    @patch.object(TrialGptEhrReadService, "get_ingest_progress")
    def test_prepare_for_read_returns_fasten_table_diseases_without_llm(
        self, mock_progress, mock_repo, mock_fasten, mock_schema
    ):
        mock_repo.has_ready_modes.return_value = False
        mock_fasten.fetch_condition_diseases.return_value = (
            ["Hypertension"],
            [{"official_name": "Hypertension", "icd10_code": None, "input": "Hypertension"}],
        )

        svc = TrialGptEhrReadService()
        prep = svc.prepare_for_read(
            patient_id="203563",
            subject_id="subj-1",
            trigger="diseases",
            sync=False,
        )

        self.assertEqual(prep["ehr_status"], "ready")
        self.assertEqual(prep["diseases"], ["Hypertension"])
        self.assertEqual(prep["disease_source"], "fastenhealth_condition")
        mock_progress.assert_called_once()

    @patch("services.trial_gpt_ehr_ingest_service.TrialGptEhrIngestService._ingest")
    @patch("services.trial_gpt_ehr_ingest_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_ingest_service.trial_gpt_ehr_repo")
    @patch("services.trial_gpt_ehr_ingest_service.get_patient_identity")
    def test_ensure_for_p2t_allows_clinical_data_without_patient_row(
        self, mock_identity, mock_repo, mock_fasten, mock_ingest
    ):
        mock_identity.return_value = {
            "mysql_patient_id": 203450,
            "subject_id": "subj-manual",
            "created_at": None,
        }
        mock_repo.has_ready_modes.return_value = False
        mock_repo.fetch_ehr_status_row.return_value = None
        mock_fasten.has_clinical_data.return_value = True
        mock_ingest.return_value = MagicMock(status="ingested")

        svc = TrialGptEhrIngestService()
        result = svc.ensure_for_p2t("203450")
        mock_ingest.assert_called_once()
        self.assertEqual(result.status, "ingested")

    @patch("services.trial_gpt_ehr_ingest_service.TrialGptEhrIngestService._ingest")
    @patch("services.trial_gpt_ehr_ingest_service.fastenhealth_repo")
    @patch("services.trial_gpt_ehr_ingest_service.trial_gpt_ehr_repo")
    @patch("services.trial_gpt_ehr_ingest_service.get_patient_identity")
    def test_ensure_for_p2t_reingests_when_fasten_tables_are_newer(
        self, mock_identity, mock_repo, mock_fasten, mock_ingest
    ):
        mock_identity.return_value = {
            "mysql_patient_id": 203563,
            "subject_id": "subj-1",
            "created_at": None,
        }
        mock_repo.has_ready_modes.return_value = True
        mock_repo.fetch_ehr_status_row.return_value = {
            "summary_status": "ready",
            "last_data_timestamp": datetime(2026, 8, 1),
        }
        mock_fasten.get_fasten_clinical_latest_ts.return_value = datetime(2026, 9, 4)
        mock_fasten.clinical_newer_than.return_value = True
        mock_fasten.has_clinical_data.return_value = True
        mock_ingest.return_value = MagicMock(status="ingested")

        svc = TrialGptEhrIngestService()
        result = svc.ensure_for_p2t("203563")
        mock_ingest.assert_called_once()
        self.assertEqual(result.status, "ingested")


if __name__ == "__main__":
    unittest.main()
