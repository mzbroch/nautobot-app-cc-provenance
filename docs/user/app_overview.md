# App Overview

This document provides an overview of the App including critical information and important considerations when applying it to your Nautobot environment.

!!! note
    Throughout this documentation, the terms "app" and "plugin" will be used interchangeably.

## Description

Config Context Provenance explains a merged config context.

Nautobot selects the config contexts that apply to an object, applies them in ascending weight order, and returns one dictionary.
The derivation is computed during that merge and discarded.
This app replays the merge and records, for every leaf path, the context that wrote it and the values that context overrode.

The app adds no models and writes nothing.
It reads config contexts that Nautobot already stores, on request.

## Audience (User Personas) - Who should use this App?

**Network engineers** who need to know which object to edit when a rendered configuration carries an unexpected value.

**Automation engineers** who layer config contexts by location, role, platform and tenant, and need to see which layer wins.

**Operators supporting a shared Nautobot** who field the question "where did this value come from?".

## Authors and Maintainers

Network to Code, LLC.

## Nautobot Features Used

The app reads `ConfigContext` objects and the `local_config_context_data` field on config-context-bearing models.
It adds a detail tab to `dcim.Device` and `virtualization.VirtualMachine` through the `TemplateExtension` API, and two read-only REST endpoints.

### Extras

The app creates no custom fields, no jobs, no relationships and no statuses.
It adds one management command, `seed_cc_provenance_demo`, which seeds demonstration data.
