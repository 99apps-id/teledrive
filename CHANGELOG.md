# Changelog

All notable changes to TeleDrive are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Production Docker Compose deployment with frontend proxy, health checks, migrations, persistent volumes, and required secrets.
- Community contribution templates and automated dependency update configuration.

### Changed

- API and worker production images now use Python 3.11 and run as non-root users.
- Deployment documentation now describes the trusted-operator alpha model, TLS, resources, and backups.
