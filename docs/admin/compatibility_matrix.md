# Compatibility Matrix

This app targets the Nautobot 2.4 LTM release train.
Each app release supports the Nautobot versions listed below, and drops support only on a major app release.

| Config Context Provenance Version | Nautobot First Support Version | Nautobot Last Support Version |
| ------------- | -------------------- | ------------- |
| 1.0.X         | 2.4.20                | 2.99.99        |

The app reads Nautobot's config context resolution and merge behaviour.
It verifies its own replay against `get_config_context()` on every request, so a change to that behaviour in a future Nautobot release surfaces as a reported mismatch rather than as a wrong answer.
