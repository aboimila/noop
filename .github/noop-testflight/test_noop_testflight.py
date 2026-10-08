"""Unit tests for the pure checks in noop_testflight.py (run on any OS):

    python3 -m unittest discover -s .github/noop-testflight -p 'test_*.py'
"""

import copy
import plistlib
import unittest
from pathlib import Path

import noop_testflight as nt

REPO = Path(__file__).resolve().parents[2]
PREFIX = "com.aboimila"
GROUP = "group.com.aboimila.noop.staging"
TEAM = "ABCDE12345"
SPECS = {s.name: s for s in nt.BUNDLES}


def good_entitlements(spec, *, distribution):
    ents = nt.render_entitlements((REPO / spec.entitlements_src).read_text(), GROUP)
    if distribution:
        ents["application-identifier"] = f"{TEAM}.{spec.bundle_id(PREFIX)}"
        ents["com.apple.developer.team-identifier"] = TEAM
        ents["get-task-allow"] = False
        ents["beta-reports-active"] = True
    return ents


def good_info(spec):
    info = {
        "CFBundleIdentifier": spec.bundle_id(PREFIX),
        "AppGroupIdentifier": GROUP,
        "CFBundleVersion": "71",
        "CFBundleShortVersionString": "12.0.0",
    }
    for key in spec.info_nonempty:
        info[key] = "usage"
    if spec.extra.get("companion"):
        info["WKCompanionAppBundleIdentifier"] = "com.aboimila.noop"
    if spec.extra.get("background_modes"):
        info["UIBackgroundModes"] = ["bluetooth-central", "location", "fetch", "processing"]
    return info


class RepoEntitlementTemplates(unittest.TestCase):
    """The tracked entitlement files are what the archive gets ad-hoc signed with, so they must
    already satisfy the checks the exported app is held to."""

    def test_every_template_resolves_and_passes(self):
        for spec in nt.BUNDLES:
            with self.subTest(spec.name):
                ents = good_entitlements(spec, distribution=False)
                self.assertEqual(nt.check_entitlements(spec, ents, GROUP, mode="adhoc", team=None, prefix=PREFIX), [])

    def test_main_app_template_has_healthkit_background_delivery(self):
        ents = good_entitlements(nt.MAIN, distribution=False)
        self.assertIs(ents[nt.HEALTHKIT], True)
        self.assertIs(ents[nt.HEALTHKIT_BACKGROUND], True)
        self.assertEqual(ents[nt.APP_GROUPS], [GROUP])

    def test_unresolved_setting_is_rejected(self):
        with self.assertRaises(nt.CheckFailed):
            nt.render_entitlements("<plist><dict><key>x</key><string>$(OTHER)</string></dict></plist>", GROUP)

    def test_bundle_ids_match_apple_registrations(self):
        self.assertEqual(
            sorted(s.bundle_id(PREFIX) for s in nt.BUNDLES),
            ["com.aboimila.noop", "com.aboimila.noop.watch", "com.aboimila.noop.watch.complications",
             "com.aboimila.noop.widgets"],
        )
        self.assertEqual(nt.app_group_for(PREFIX), GROUP)


class EntitlementChecks(unittest.TestCase):
    def test_distribution_passes(self):
        for spec in nt.BUNDLES:
            ents = good_entitlements(spec, distribution=True)
            self.assertEqual(nt.check_entitlements(spec, ents, GROUP, mode="distribution", team=TEAM, prefix=PREFIX), [])

    def test_missing_capabilities_fail(self):
        for key in (nt.HEALTHKIT, nt.HEALTHKIT_BACKGROUND, nt.APP_GROUPS):
            ents = good_entitlements(nt.MAIN, distribution=True)
            del ents[key]
            with self.subTest(key):
                self.assertTrue(nt.check_entitlements(nt.MAIN, ents, GROUP, mode="distribution", team=TEAM, prefix=PREFIX))

    def test_watch_without_healthkit_fails(self):
        spec = SPECS["NOOPWatch"]
        ents = good_entitlements(spec, distribution=True)
        ents[nt.HEALTHKIT] = False
        self.assertTrue(nt.check_entitlements(spec, ents, GROUP, mode="distribution", team=TEAM, prefix=PREFIX))

    def test_wrong_group_fails(self):
        spec = SPECS["NOOPWidgets"]
        ents = good_entitlements(spec, distribution=False)
        ents[nt.APP_GROUPS] = ["group.com.noopapp.noop.staging"]
        self.assertTrue(nt.check_entitlements(spec, ents, GROUP, mode="adhoc", team=None, prefix=PREFIX))

    def test_development_signature_fails(self):
        ents = good_entitlements(nt.MAIN, distribution=True)
        ents["get-task-allow"] = True
        del ents["beta-reports-active"]
        problems = nt.check_entitlements(nt.MAIN, ents, GROUP, mode="distribution", team=TEAM, prefix=PREFIX)
        self.assertEqual(len(problems), 2)


class InfoAndVersionChecks(unittest.TestCase):
    def test_good_info_passes(self):
        for spec in nt.BUNDLES:
            self.assertEqual(nt.check_info(spec, good_info(spec), PREFIX, GROUP), [])

    def test_bluetooth_and_health_permissions_required(self):
        for key in ("NSBluetoothAlwaysUsageDescription", "NSHealthShareUsageDescription",
                    "NSHealthUpdateUsageDescription"):
            info = good_info(nt.MAIN)
            info[key] = " "
            with self.subTest(key):
                self.assertTrue(nt.check_info(nt.MAIN, info, PREFIX, GROUP))
        info = good_info(nt.MAIN)
        info["UIBackgroundModes"] = ["location"]
        self.assertTrue(nt.check_info(nt.MAIN, info, PREFIX, GROUP))

    def test_watch_companion_must_be_main_app(self):
        spec = SPECS["NOOPWatch"]
        info = good_info(spec)
        info["WKCompanionAppBundleIdentifier"] = "com.noopapp.noop"
        self.assertTrue(nt.check_info(spec, info, PREFIX, GROUP))

    def test_versions(self):
        infos = {s.name: good_info(s) for s in nt.BUNDLES}
        self.assertEqual(nt.check_versions(infos, "71"), [])
        self.assertTrue(nt.check_versions(infos, "72"))
        infos["NOOPWidgets"]["CFBundleVersion"] = "435"
        self.assertTrue(nt.check_versions(infos, "71"))


class ProfileAndAuthorityChecks(unittest.TestCase):
    def profile(self, spec):
        ents = good_entitlements(spec, distribution=True)
        return {"TeamIdentifier": [TEAM], "Name": "iOS Team Store Provisioning Profile", "Entitlements": ents}

    def test_app_store_profile_passes(self):
        for spec in nt.BUNDLES:
            self.assertEqual(nt.check_profile(spec, self.profile(spec), team=TEAM, prefix=PREFIX, app_group=GROUP), [])

    def test_development_profile_fails(self):
        prof = self.profile(nt.MAIN)
        prof["ProvisionedDevices"] = ["00008110-000000000000001E"]
        prof["Entitlements"]["get-task-allow"] = True
        self.assertEqual(len(nt.check_profile(nt.MAIN, prof, team=TEAM, prefix=PREFIX, app_group=GROUP)), 2)

    def test_profile_without_background_delivery_fails(self):
        prof = self.profile(nt.MAIN)
        del prof["Entitlements"][nt.HEALTHKIT_BACKGROUND]
        self.assertTrue(nt.check_profile(nt.MAIN, prof, team=TEAM, prefix=PREFIX, app_group=GROUP))

    def test_authority(self):
        ok = "Executable=x\nAuthority=Apple Distribution: Someone (ABCDE12345)\nAuthority=Apple Worldwide Developer Relations Certification Authority\n"
        dev = "Authority=Apple Development: Someone (ABCDE12345)\n"
        self.assertEqual(nt.check_authority(nt.MAIN, ok), [])
        self.assertTrue(nt.check_authority(nt.MAIN, dev))
        self.assertTrue(nt.check_authority(nt.MAIN, "Signature=adhoc\n"))


class StructureAndSettings(unittest.TestCase):
    def test_unexpected_bundles(self):
        known = [s.rel_path for s in nt.BUNDLES if s.rel_path]
        self.assertEqual(nt.unexpected_bundles(known), [])
        self.assertEqual(nt.unexpected_bundles(known + ["PlugIns/Other.appex"]), ["PlugIns/Other.appex"])

    def test_build_settings(self):
        for spec in nt.BUNDLES:
            settings = {
                "PRODUCT_BUNDLE_IDENTIFIER": spec.bundle_id(PREFIX),
                "APP_GROUP_ID": GROUP,
                "CODE_SIGN_ENTITLEMENTS": spec.entitlements_src,
                "SKIP_INSTALL": "NO" if spec is nt.MAIN else "YES",
            }
            self.assertEqual(nt.check_build_settings(spec, settings, PREFIX, GROUP), [])
            bad = dict(settings, SKIP_INSTALL="NO" if spec is not nt.MAIN else "YES")
            self.assertTrue(nt.check_build_settings(spec, bad, PREFIX, GROUP))

    def test_entitlement_paths_match_project_yml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        spec = yaml.safe_load((REPO / "project.yml").read_text())
        for b in nt.BUNDLES:
            target = spec["targets"][b.target]
            self.assertEqual(target["entitlements"]["path"], b.entitlements_src)
            self.assertEqual(target["settings"]["base"]["PRODUCT_BUNDLE_IDENTIFIER"],
                             "$(BUNDLE_ID_PREFIX)" + b.id_suffix)
            self.assertEqual(target["info"]["properties"]["AppGroupIdentifier"], "$(APP_GROUP_ID)")
        self.assertEqual(spec["settings"]["base"]["APP_GROUP_ID"], "group.$(BUNDLE_ID_PREFIX).noop.staging")
        self.assertEqual(spec["targets"]["NOOPWatch"]["info"]["properties"]["WKCompanionAppBundleIdentifier"],
                         "$(BUNDLE_ID_PREFIX).noop")


if __name__ == "__main__":
    unittest.main()
