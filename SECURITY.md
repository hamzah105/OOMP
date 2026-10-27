# Security policy

OOMP 0.1.0 is an alpha local research candidate. Supported fixes currently target
the current main/release-candidate line; there is no enterprise support team or
guaranteed response time. See [security assumptions](docs/security-model.md),
[privacy/retention](docs/privacy-retention.md) and [limitations](docs/limitations.md).

## Reporting

Do not publish exploit details, tokens, private source content or a database in
public issues. GitHub's repository **Report a vulnerability** interface is the
preferred private method **when the maintainer has enabled it**. Availability has
not been assumed or configured by this change. The maintainer must enable private
vulnerability reporting in repository Settings → Security before inviting private
reports or publishing the candidate. No private email address is invented here.

If the private interface is unavailable, a nonsensitive
[repository issue](https://github.com/hamzah105/OOMP/issues) can request a private
contact without describing the exploit, affected personal data or credentials.
Maintainers should establish a private channel before receiving those details.
GitHub's [private reporting instructions](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/privately-reporting-a-security-vulnerability)
describe the actual supported mechanism; this policy is not proof it is enabled.

Include versions, affected surface, impact, a minimal synthetic reproduction and
suggested mitigation through that private channel. Separate confirmed behavior
from speculation. Coordinate remediation/disclosure with the maintainer; rotate
compromised credentials and handle affected backups through your local policy.

## Deployment boundary

Scope objects rely on trusted local callers. SQLite is plaintext and local;
administrators control files. The HTTP MCP profile requires explicit loopback
grants/Host/Origin checks and is not a public cloud deployment profile. Signing
keys remain in the trusted host; models have no erasure/approval tool. Erasure
does not securely wipe external copies or old backups. A dependency scan and
passing tests are evidence for the exercised version, not a guarantee of absence
of vulnerabilities. See [the focused review](docs/security-review.md).
