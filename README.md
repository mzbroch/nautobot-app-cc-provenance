# Config Context Provenance

<p align="center">
  <img src="https://raw.githubusercontent.com/nautobot/nautobot-app-cc-provenance/develop/docs/images/icon-cc-provenance.png" class="logo" height="200px">
  <br>
  <a href="https://github.com/nautobot/nautobot-app-cc-provenance/actions"><img src="https://github.com/nautobot/nautobot-app-cc-provenance/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <a href="https://docs.nautobot.com/projects/cc-provenance/en/latest/"><img src="https://readthedocs.org/projects/nautobot-plugin-cc-provenance/badge/"></a>
  <br>
  An App for <a href="https://github.com/nautobot/nautobot">Nautobot</a>.
</p>

## Overview

Nautobot resolves the config contexts that apply to an object, merges them in weight order, and returns a single dictionary.
The mapping from each key back to the context that supplied it is computed during that merge and then discarded.

This app replays the same merge and keeps the mapping.

For any device or virtual machine, it answers two questions the merged config context cannot:

- **Which context set this key?** Each leaf path names the context object that won it, with that context's weight and owner.
- **What did that context override?** Every shadowed value is listed with the context that supplied it.

The app adds a **Context Provenance** tab to the device and virtual machine detail pages, plus a read-only REST endpoint.

### Screenshots

The tab lists one row per leaf path in the merged config context.
Select the shadow count on a contested path to see what it overrode.

```
Path                        Value              Source                   Weight  Shadowed
intended-firmware.version   "5.12.0-local"     Local config context     —       3
features                    "disabled"         CCP Spine Override       1800    1
tiebreak.winner             "zzz"              CCP Tiebreak ZZZ         1700    1
ntp.servers            list ["10.1.0.1"]       CCP Region EMEA          1200    1
```

## Try it out

The app ships a management command that seeds a worked example: three sites, five devices, and nine layered config contexts.

```bash
nautobot-server seed_cc_provenance_demo
```

The command prints a link to each device and what that device demonstrates.
Run it again with `--flush` to remove everything it created.

## Documentation

Full documentation is published on [Read the Docs](https://docs.nautobot.com/projects/cc-provenance/en/latest/):

- [User Guide](https://docs.nautobot.com/projects/cc-provenance/en/latest/user/app_overview/) — what the app does and how to read the tab.
- [Administrator Guide](https://docs.nautobot.com/projects/cc-provenance/en/latest/admin/install/) — how to install and configure it.
- [Developer Guide](https://docs.nautobot.com/projects/cc-provenance/en/latest/dev/contributing/) — how to extend and contribute.

## Questions

For any questions or comments, please check the [FAQ](https://docs.nautobot.com/projects/cc-provenance/en/latest/user/faq/) first.
Sign up for [Network to Code's Slack](https://slack.networktocode.com/) and join the `#nautobot` channel.
