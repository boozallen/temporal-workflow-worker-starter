# Security Policy

## Supported Versions

This repository is a fork-and-customize template rather than a released library. Only the
latest release on the default branch receives security updates. Once you fork it, your
fork is yours to maintain — security fixes made here do not propagate to existing forks,
so track this repository if you want to pick them up.

| Version | Supported |
|---------|-----------|
| Latest release | Yes |
| Previous releases | No |
| Your fork | Maintained by you |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

To report a vulnerability, submit a Draft Security Advisory to the
administrators of this project:

1. Navigate to the **Security** tab of this repository
2. Click **Report a vulnerability** (under "Advisories")
3. Fill in the details of the vulnerability
4. Submit the draft advisory

This uses GitHub's private security advisory feature, ensuring your report
remains confidential until a fix is available.

### What to Include

- Description of the vulnerability
- Which files or components are affected, and the version or commit
- Steps to reproduce
- Potential impact, including whether it affects the template itself or only a
  customized fork
- Any suggested fix (optional)

### What to Expect

- Acknowledgment within 5 business days
- Regular updates on the status of your report
- Credit in the advisory (unless you prefer to remain anonymous)

We will work with you to understand the issue and coordinate disclosure.

## Vulnerabilities in Dependencies

This template composes the
[`temporal-packages`](https://github.com/boozallen/temporal-packages) libraries. Report
vulnerabilities in those packages on that repository so the fix lands where the code
lives. If you are unsure which repository owns the issue, report it here and we will
route it.

## Preferred Languages

We accept vulnerability reports in English.
