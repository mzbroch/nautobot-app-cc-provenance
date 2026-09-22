# Getting Started with the App

This document provides a step-by-step tutorial on how to get the App going and how to use it.

## Install the App

To install the App, please follow the instructions detailed in the [Installation Guide](../admin/install.md).

## First steps with the App

The app needs no configuration.
Once installed, every device and virtual machine detail page carries a **Context Provenance** tab.

If your instance has no layered config contexts yet, seed a worked example:

```no-highlight
nautobot-server seed_cc_provenance_demo
```

The command creates three sites, five devices and nine config contexts scoped by location, role, platform and tenant.
Every object it creates is named with a `CCP` prefix, and the config contexts are scoped to the demo sites, so seeding does not change the config context of any device that already exists.

The command prints a link to each seeded device and what that device demonstrates.

Remove everything it created:

```no-highlight
nautobot-server seed_cc_provenance_demo --flush
```

## What are the next steps?

Read [Using the App](app_use_cases.md) for the workflows the tab supports.

Query the same data over REST:

```no-highlight
curl -s -H "Authorization: Token $TOKEN" \
  "https://nautobot.example.com/api/plugins/cc-provenance/config-context-provenance/devices/$DEVICE_ID/"
```

Add `?conflicts_only=true` to return only the contested paths.
Virtual machines use `/config-context-provenance/virtual-machines/$VM_ID/`.

When the replay cannot reproduce the object's own `get_config_context()`, the tab shows the diverging paths and the endpoint returns `409 Conflict`.
The app reports that it cannot answer rather than naming a source that might be wrong.
