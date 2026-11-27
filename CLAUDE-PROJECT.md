# CLAUDE-PROJECT.md

Rules, tools and paths of PCM-Adapter, the repository of the VCF vCommunity Adapter. Loaded with [CLAUDE.md](CLAUDE.md), which holds the method. This repository is one of several; work across them follows the workspace's [CLAUDE-PROJECT.md](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/CLAUDE-PROJECT.md).

## Files of the method

- Roadmap, open questions and decisions that bind several repositories: the workspace's [ROADMAP.md](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/ROADMAP.md), [OPEN-QUESTIONS.md](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/OPEN-QUESTIONS.md) and [DECISIONS.md](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/DECISIONS.md).
- No milestone hook runs here. Before acting, read the open milestone in the workspace's ROADMAP.md: the first heading that does not end with ": done".
- Requirements of this repository: [`spec/requirements/`](spec/requirements) (WD-036). The KPI definitions' contract requirements are in the workspace's [kpi-definitions.md](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/spec/requirements/kpi-definitions.md). Each requirement belongs to the workspace milestone that ROADMAP.md names.
- Questions inside this repository: [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md), IDs Q-ADP-n (WD-019, WD-038).

## VCF vCommunity Adapter

A Python adapter (`Management Pack/app`) that collects extra properties and metrics from vCenter and publishes them onto the existing vCenter objects in VCF Operations under the `vCommunity|` key prefix.

- Its repository is PCM-Adapter; the management pack's name is VCF vCommunity Adapter (WD-032).
- Contracts with the other repositories, the decisions that bind several of them, releases and milestones: [private-cloud-workspace](https://github.com/e1-rahabok/private-cloud-workspace).

## Documentation

Pages go in `docs/` by the rules in [CONTRIBUTING.md](CONTRIBUTING.md#documentation). Add every new page to the contents in `docs/README.md`.

## Building

```
pwsh tools/build/build.ps1
```

Builds the `.pak` into `Management Pack/build` and pushes the adapter image to `ghcr.io/e1-rahabok/vcf-operations-vcommunity`. Don't call `mp-build` directly from a non-interactive shell: it crashes without a Windows console, and it waits on a prompt if `config.json` (gitignored) has no registry. The script handles both. Details: [tools/build/build.md](tools/build/build.md). All tools: [tools/README.md](tools/README.md).

## Installing on the test instance

```
pwsh tools/install/install.ps1
```

Uploads and installs the newest pak for the `manifest.txt` version (unsigned, signature checking ignored). Run it directly, as part of one end-to-end process. Do not ask the user to type or run anything for the install. If the platform blocks the script, report the block and stop. Do not work around it. Then run `pwsh tools/restart/restart.ps1` (the Adapter Instances of the VCF vCommunity Adapter often stop collecting after an upgrade), wait one collection cycle, and run the live validation. Details: [tools/install/install.md](tools/install/install.md), [tools/restart/restart.md](tools/restart/restart.md).

## Releasing

A release is its pak. Every GitHub release gets the validated `vCommunity_<version>.pak` attached, after the sign-off in [tools/validate/validate.md](tools/validate/validate.md#release-sign-off) passes (`validate.ps1 -ExpectedVersion <version> -Release`).

## Screenshots

```
pwsh tools/screenshot/screenshot.ps1
```

Takes the docs' screenshots of the VCF Operations UI from the instance, as defined in `tools/screenshot/screenshots.json`, logging in like `install.ps1`. Use it to take or update screenshots, never Claude in Chrome. To add one, ask the user for an example of the part of the screen once, add an entry, and run it with `-Name` and `-SaveSteps` until it matches. Details: [tools/screenshot/screenshot.md](tools/screenshot/screenshot.md).

## Testing

Run both layers after any change under `Management Pack/app`, and report the results of each.

Until the workspace's milestone M8, a cloud session cannot reach the lab: it runs the unit tests, reports the live validation as not run, lists it in the pull request for M8's lab session, and goes on. WD-042 records the author's answer to CLAUDE.md's stop rule for the lab.

1. **Unit tests** (fakes, no live system). From the `Management Pack` folder:

   ```
   python -m pytest tests
   ```

2. **Live validation** (read-only, against the VCF Operations test instance):

   ```
   pwsh tools/validate/validate.ps1
   ```

   - Reads the URL and login from `.secrets/vcf-ops.xml` (gitignored, never commit or print it).
   - Exits 0 on pass, 1 on any FAIL. WARN lines are worth mentioning but do not fail the run.
   - It tests the build **installed on the instance**, not the code in this repo. A code change is only covered once that build has been installed there; say so plainly if it has not.

If a layer cannot be run (for example Python is not installed), say that instead of skipping it silently.
