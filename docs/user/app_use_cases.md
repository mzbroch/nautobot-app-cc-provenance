# Using the App

This document describes common use-cases and scenarios for this App.

## General Usage

Open any device or virtual machine and select the **Context Provenance** tab.
The tab lists one row per leaf path in the merged config context.

| Column | Meaning |
| :----- | :------ |
| Path | The dotted path of the value, such as `intended-firmware.version`. |
| Value | The merged value, rendered as JSON. |
| Source | The config context that supplied the value, with its owner when a Git repository provides it. |
| Weight | The weight at which that context applied. Local data shows an em dash, because it has no weight. |
| Shadowed | How many earlier values this path overrode. Select the count to list them. |

Select **Conflicts only** to hide the paths that have a single source.
On a fabric with layered contexts, most paths have one source and nothing to investigate.

## Use-cases and common workflows

### Find the object that set a wrong value

A rendered configuration carries a firmware version nobody expected.
Open the device, select **Context Provenance**, and filter for `firmware`.
The Source column names the context to edit, and the shadow list shows what that context overrode.

### Understand why a high-weight context lost

Nautobot applies contexts in ascending weight order, so the highest weight wins by being applied last.
Local config context data applies after every context and cannot be outranked.
When a context you expected to win did not, the tab shows which layer came after it.

### Audit a path across the fabric

Request the REST endpoint for several devices and compare the `source` of one path.
A path whose source differs between two devices in the same role usually means a scope is wider or narrower than intended.

## Screenshots

Run the seed command to populate a worked example, then open the devices it prints:

```no-highlight
nautobot-server seed_cc_provenance_demo
```

The seeded data demonstrates one behaviour per device:

| Device | Behaviour |
| :----- | :-------- |
| `ccp-ams01-leaf01` | Local data outranks every context. `intended-firmware.version` has three shadowed values. |
| `ccp-ams01-spine01` | A scalar replaces a whole subtree. `features` collapses `features.evpn` into its shadow list. |
| `ccp-fra01-leaf01` | Lists are single paths. Deep merge replaces a list wholesale rather than merging elements. |
| `ccp-dfw01-leaf01` | Equal weights break on name, ascending. `tiebreak.winner` resolves to `zzz`. |
