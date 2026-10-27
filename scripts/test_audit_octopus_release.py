"""Adversarial evidence tests: green tasks cannot substitute for exact source proof."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("octopus_audit", Path(__file__).with_name("audit-octopus-release.py"))
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


class ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"components": {name: {"repository": "ayahos-hq/" + name,
                                              "git_sha": "a" * 40}
                                         for name in audit_module.REPOS}}
        self.release = {"Id": "Releases-1", "SpaceId": "Spaces-1", "ProjectId": "Projects-21",
                        "ProjectDeploymentProcessSnapshotId": "snapshot", "SelectedGitResources": []}
        self.process = {"Id": "snapshot", "ProjectId": "Projects-21", "Steps": []}
        nodes = []
        for name in sorted(audit_module.REPOS):
            self.release["SelectedGitResources"].append({"ActionName": name,
                "GitResourceReferenceName": "", "GitReferenceResource": {"GitCommit": "a" * 40}})
            self.process["Steps"].append({"Name": name, "Condition": "Success", "Actions": [{
                "Name": name, "GitDependencies": [{"Name": "", "RepositoryUri":
                                                   f"https://github.com/ayahos-hq/{name}.git"}]}]})
            nodes.append({"Name": f"Step {len(nodes) + 1}: {name}", "Status": "Success"})
        self.task = {"Id": "ServerTasks-1", "SpaceId": "Spaces-1", "State": "Success",
                     "Arguments": {"DeploymentId": "Deployments-1"}}
        self.deployment = {"Id": "Deployments-1", "ProjectId": "Projects-21",
                           "ReleaseId": "Releases-1", "TaskId": "ServerTasks-1"}
        self.details = {"Task": {"Id": "ServerTasks-1"}, "ActivityLogs": [{"Children": nodes}]}

    def report(self):
        return audit_module.audit(self.manifest, "a" * 40, self.release, self.process,
                                  self.task, self.deployment, self.details)

    def test_five_exact_successful_sources_are_still_not_production_acceptance(self):
        report = self.report()
        self.assertTrue(report["source_coverage_passed"])
        self.assertFalse(report["production_accepted"])

    def test_old_platform_sha_blocks_green_release(self):
        self.release["SelectedGitResources"][2]["GitReferenceResource"]["GitCommit"] = "b" * 40
        self.assertFalse(self.report()["source_coverage_passed"])

    def test_partial_project_cannot_attest_five_repos(self):
        self.process["Steps"] = self.process["Steps"][:2]
        self.assertEqual(len(self.report()["covered_repositories"]), 2)
        self.assertFalse(self.report()["source_coverage_passed"])

    def test_skipped_or_missing_step_cannot_hide_behind_successful_task(self):
        for status in ("Skipped", "Failed", None):
            with self.subTest(status=status):
                self.details["ActivityLogs"][0]["Children"][0]["Status"] = status
                self.assertFalse(self.report()["source_coverage_passed"])

    def test_release_task_and_snapshot_must_be_linked(self):
        for record, key in ((self.deployment, "ReleaseId"), (self.deployment, "TaskId"),
                            (self.process, "Id"), (self.release, "ProjectId")):
            with self.subTest(key=key):
                prior = record[key]
                record[key] = "unrelated"
                with self.assertRaises(ValueError):
                    self.report()
                record[key] = prior

    def test_disabled_step_and_failed_task_block_source_coverage(self):
        self.process["Steps"][0]["IsDisabled"] = True
        self.assertFalse(self.report()["source_coverage_passed"])
        self.process["Steps"][0].pop("IsDisabled")
        self.task["State"] = "Failed"
        self.assertFalse(self.report()["source_coverage_passed"])

    def test_duplicate_resource_is_ambiguous(self):
        self.release["SelectedGitResources"].append(copy.deepcopy(self.release["SelectedGitResources"][0]))
        with self.assertRaises(ValueError):
            self.report()

    def test_child_errors_do_not_disclose_credentials(self):
        with patch.object(audit_module.subprocess, "run", side_effect=FileNotFoundError("secret-value")):
            with self.assertRaises(ValueError) as error:
                audit_module.api("/api/tasks/ServerTasks-1")
        self.assertNotIn("secret-value", str(error.exception))


if __name__ == "__main__":
    unittest.main()
