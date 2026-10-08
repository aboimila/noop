# NOOP: personal TestFlight deployment (aboimila/noop)

This fork builds the native NOOP iOS app under **your own** Apple identifiers, signs it for App
Store Connect, and uploads it to **TestFlight** for **internal testing only**. It is a personal,
noncommercial install for connecting a WHOOP 4.0 strap to Apple Health. Nothing here publishes an
App Store release, and the upstream release, testing and sideload workflows are unchanged.

| What | Value |
|---|---|
| Workflow | `.github/workflows/noop-testflight.yml`, shown as **NOOP TestFlight (personal)** |
| Helper | `.github/noop-testflight/noop_testflight.py` (signing preparation and verification) |
| App Store Connect app | Aboimila Health Bridge |
| iOS app | `com.aboimila.noop` (shows as **NOOP** on the Home Screen) |
| Widget extension | `com.aboimila.noop.widgets` |
| Apple Watch app | `com.aboimila.noop.watch` |
| Watch complications | `com.aboimila.noop.watch.complications` |
| App Group (all four) | `group.com.aboimila.noop.staging` |
| Secrets used | `APPSTORE_API_KEY_ID`, `APPSTORE_API_ISSUER_ID`, `APPSTORE_API_PRIVATE_KEY`, `APPLE_TEAM_ID` |

## How it works

1. **Identifiers.** CI writes the gitignored `Config/BundleIdSecrets.xcconfig` containing only
   `BUNDLE_ID_PREFIX = com.aboimila`. That is the upstream mechanism: `project.yml` derives every
   bundle id, the App Group and the watch's companion id from it. No tracked file changes.
2. **Project.** XcodeGen generates the project from `project.yml` plus a small CI-only overlay
   (`.github/noop-testflight/project.testflight.yml`) that sets `SKIP_INSTALL=YES` on the widget
   extension, so the App Store archive contains exactly one installed product (`NOOP.app`). A
   build-settings check then confirms bundle ids, the App Group, the entitlement files and
   `SKIP_INSTALL` for all four targets.
3. **Archive.** `NOOPiOS` is archived in Release for a generic iOS device **unsigned**
   (`CODE_SIGNING_ALLOWED=NO`). This stops Xcode from asking Apple for a *development* profile,
   which would need a registered device. The build number is set once on the command line, so the
   app, the widget, the watch app and the complication all carry the same `CFBundleVersion`.
4. **Entitlements.** An unsigned binary carries no entitlements, and the App Store export re-signs
   with whatever each archived binary declares. The helper therefore ad-hoc signs (no certificate,
   no profile, no device) each bundle inside out (complication, watch app, widget, app), using its
   own tracked entitlement file with the App Group filled in. It then checks the archive.
5. **Distribution signing.** `xcodebuild -exportArchive` with `method = app-store-connect`,
   `signingStyle = automatic` and the API key. Xcode uses (or creates) an **Apple Distribution**
   certificate and an **App Store** provisioning profile for each of the four App IDs. App Store
   profiles have no device list. The options also set `testFlightInternalTestingOnly`.
6. **Verification gate.** The exported `.ipa` is unpacked, and the run **fails** unless every bundle
   meets all of the following:
   - It is signed by *Apple Distribution*, with an App Store profile from your team for its exact
     App ID: no devices, no `get-task-allow`. The app itself must also have `beta-reports-active`.
   - It has the right bundle id, build number, version and `AppGroupIdentifier`.
   - **App:** `com.apple.developer.healthkit`, `com.apple.developer.healthkit.background-delivery`
     and the App Group entitlement, each granted by its profile. Also the `bluetooth-central`
     background mode and the Bluetooth, Health-read and Health-write usage strings.
   - **Watch app:** HealthKit, the App Group, its Health usage strings, and
     `WKCompanionAppBundleIdentifier = com.aboimila.noop`.
   - **Widget and complication:** the App Group.
   - `codesign --verify --deep --strict` passes on the whole app.

   Team ids are redacted from the log.
7. **Upload** (only when requested, and only from `main`). The same archive is exported again with
   `destination = upload`. Apart from the destination, the options are identical to the run that
   was just verified. The build goes to App Store Connect.

| Trigger | What happens | Apple secrets used? |
|---|---|---|
| Pull request to `main` touching native code or this setup | Unsigned archive, entitlement embedding, archive checks | **No** |
| Push to `main` touching native source (`Strand/`, `StrandiOS*/`, `NOOPWatch*/`, `Packages/`, `Config/`, `project.yml`, `Package.resolved`) | Archive, sign, verify, **upload** | Yes |
| **Run workflow**, `upload` unticked (default) | Archive, sign, verify. Nothing uploaded | Yes |
| **Run workflow**, `upload` ticked, branch `main` | Archive, sign, verify, **upload** | Yes |

A change to only the workflow or its helper does **not** upload on its own, so merging this setup
never sends a build by itself. Syncing the fork with upstream counts as a push to `main`, so when
the sync brings in native changes, a new TestFlight build follows automatically.

**Build numbers** are `run_number × 10 + attempt` (for example, run 7 → build `71`; a re-run of the
same run → `72`). They only ever increase. The marketing version is upstream's `MARKETING_VERSION`
from `project.yml`, currently 12.0.0.

## 1. Run a signing and export test (no upload)

1. Merge the pull request that adds this workflow.
2. GitHub → **Actions** → **NOOP TestFlight (personal)** → **Run workflow**.
3. Branch: **main**. Leave **upload** **unticked**. Click **Run workflow**.
4. Expect about 25 to 45 minutes. Success means the job summary says *"Signed for App Store
   distribution and capabilities verified. Not uploaded"*. The **Verify the signed app's
   capabilities** step lists each bundle's entitlements and ends with
   `✓ all 4 bundles passed distribution verification`.

If the export or the verification fails, see [Troubleshooting](#troubleshooting).

## 2. Trigger the first TestFlight upload

Run the workflow again on **main** with **upload** **ticked**. When the **Upload to TestFlight** step
succeeds, App Store Connect has accepted the build.

After that, every push to `main` that changes native source uploads automatically. You can still
upload on demand at any time with **Run workflow** and **upload** ticked.

## 3. Find the build in App Store Connect

1. Open <https://appstoreconnect.apple.com> → **Apps** → **Aboimila Health Bridge** → **TestFlight**.
2. Under **iOS Builds**, open version **12.0.0**. The new build number is listed with status
   *Processing*. Processing usually takes 5 to 30 minutes, and Apple emails you when it finishes.
3. **Export compliance.** NOOP's `Info.plist` does not declare `ITSAppUsesNonExemptEncryption`, so
   each build shows **Missing Compliance** until you answer the encryption question (**Manage**
   next to the warning). That answer is a legal declaration and is yours to make, so the workflow
   does not make it for you. Apple's guidance is that an app whose only encryption is the HTTPS/TLS
   built into Apple's operating system generally qualifies as exempt. Check that against what this
   build does before you answer. If you want to stop being asked for every build, a later change
   can set the key in the CI overlay.

## 4. Add yourself as an internal tester

1. App Store Connect → **Users and Access**. Make sure your Apple Account is listed. The Account
   Holder always is.
2. **Apps → Aboimila Health Bridge → TestFlight → Internal Testing →** click **＋** next to the
   heading. Create a group, for example *Me*, and optionally tick **Enable automatic distribution**
   so every new build reaches the group without any clicks.
3. Open the group → **Testers → ＋** → select yourself → **Add**.
4. If you did not enable automatic distribution, open the group → **Builds → ＋** and add the
   processed build.

Internal testing needs **no Beta App Review**. Do not create an external group or submit for
review: this build is meant for internal TestFlight only. The export also requests internal-only
testing (`testFlightInternalTestingOnly`).

## 5. Install with TestFlight

1. On your iPhone, install **TestFlight** from the App Store and sign in with the same Apple Account.
2. Accept the invitation email, or open TestFlight directly. **NOOP** appears there. Tap **Install**.
3. **Apple Watch:** the watch app rides inside the iPhone app. Open the **Watch** app on your iPhone
   → **My Watch** → scroll to **NOOP** → **Install**, unless iOS installs it automatically.
4. A TestFlight build expires after 90 days. Any newer upload replaces it.

The TestFlight app uses `com.aboimila.noop` and its own App Group, so it installs **beside** any
sideloaded NOOP (`com.noopapp.noop`) and does **not** share its data. To move data across, use
**Backup & Sync** in the old install to export a `.noopbak`, then import that file in the new one.

## 6. Verify Apple Health reading and writing

1. Open NOOP → **More** → **Data** → **Apple Health** → **Enable Apple Health**. The iOS Health
   permission sheet should appear, listing both **read** and **write** categories. Allow the ones
   you want.
   - If the screen instead says *"This install can't connect to Apple Health directly…"*, the
     installed build lacks the HealthKit entitlement. That should not happen, because the workflow
     blocks such builds. Report the run number if it does.
2. iPhone **Settings → Health → Data Access & Devices → NOOP**. NOOP should be listed, with
   **Allow "NOOP" to Write Data** and **Allow "NOOP" to Read Data** sections.
3. **Read:** back on NOOP's Apple Health screen, the status should say *Connected* with a *Last
   synced …* time once the history import finishes.
4. **Write:** pair the WHOOP 4.0 strap, let it sync, then open the **Health** app → **Browse** →
   **Heart** → **Heart Rate** → **Show All Data** (or **Data Sources & Access**). Samples from
   **NOOP** should appear. Sleep, workouts and nightly vitals are written as the strap's data is
   processed.
5. **Background:** lock the phone for a while with the strap nearby, then reopen NOOP. Bluetooth
   collection should have continued (the `bluetooth-central` background mode). New Health
   samples should keep appearing, with periodic background refresh when iOS allows it.

## Manual Apple configuration still to check

These steps happen in Apple's portals, so the workflow cannot do them for you:

- **API key role.** Creating or using the cloud-managed Apple Distribution certificate and creating
  App Store profiles through the API needs an App Store Connect API key with the **Admin** role
  (Users and Access → Integrations → App Store Connect API). A *Developer* key cannot do it, and
  the export then fails with a certificate or profile permission error.
- **Capabilities on each App ID** (developer.apple.com → Certificates, Identifiers & Profiles →
  Identifiers). The verification gate checks for exactly these:
  - `com.aboimila.noop`: **HealthKit** and **App Groups** (`group.com.aboimila.noop.staging`).
  - `com.aboimila.noop.watch`: **HealthKit** and **App Groups**.
  - `com.aboimila.noop.widgets` and `com.aboimila.noop.watch.complications`: **App Groups**.

  Note that the watch's App Group must actually be *assigned* on its App ID, not just exist.
- **Stale profiles.** If you hand-made App Store profiles for these App IDs before enabling every
  capability, delete them (Profiles list). Automatic signing then generates fresh ones that include
  HealthKit background delivery and the App Group.
- **Export compliance** for each build, as described in step 3, unless you later automate it.
- **Upstream workflows in this fork.** Upstream's `app-build.yml` and the other PR checks still run
  on your pull requests. `fork-release.yml` and `fork-testing-build.yml` only run when dispatched by
  hand and never touch TestFlight. Don't run `fork-release.yml` here: it commits version bumps
  and publishes GitHub releases.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `Check identifiers, App Group and entitlement files` fails | Upstream renamed a target or an entitlement path. Update `BUNDLES` in `noop_testflight.py` to match `project.yml`. |
| `archive is not a single-app iOS archive` | A newly added embedded target installs itself. Add `SKIP_INSTALL: YES` for it in `project.testflight.yml`. |
| `unknown nested bundles would be signed without entitlements` | Upstream added an extension or app. Add it to `BUNDLES`, with its entitlement file, before shipping. |
| Export: *"No profiles for 'com.aboimila.noop…' were found"* / *"not permitted to create certificates"* | The API key lacks the Admin role, or the App ID does not exist under this team. |
| Export: *"Provisioning profile … doesn't include the com.apple.developer.healthkit.background-delivery / application-groups entitlement"* | Enable the capability or assign the App Group on that App ID, delete stale profiles, then re-run. |
| `provisioning profile does not grant …` in the verification step | Same fix as the line above. The gate stopped a build that would have shipped without the capability. |
| Upload: *"The bundle version must be higher…"* / *"already been used"* | Only possible after manual build-number changes. Re-run the workflow: the next run number is higher. |
| `APPSTORE_API_PRIVATE_KEY is not a .p8 private key` | Paste the whole `AuthKey_XXXX.p8` file, including the `BEGIN`/`END` lines, or its base64 encoding. |

## What was tested where

- **Linux (while writing this):**
  - The helper's unit tests (`python3 -m unittest discover -s .github/noop-testflight -p 'test_*.py'`).
    These check the tracked entitlement files, bundle ids, the App Group, and the
    distribution/profile/authority rules.
  - YAML parsing and `bash -n` on every workflow step.
  - The ExportOptions plist rendering.
  - An emulation of XcodeGen's include-merge for the overlay.
- **Only on the macOS runner:** XcodeGen, `xcodebuild`, `codesign`, the App Store Connect API and
  the upload. The first **Run workflow** with `upload` unticked is the real end-to-end test of
  signing and export.
