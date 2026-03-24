# Contributing Guide

## How to Contribute

### Important Guidelines

1. **Keep all changes as commits to this repository**
   - Use version control for all modifications
   - Push commits regularly to maintain code history
   - Never force-push to shared branches

2. **Add your name as a contributor**
   - Update the [Contributors](#contributors) section below
   - Include your name, time period, and major contributions

3. **Document your work in the changelog**
   - Create a markdown folder with your name in `docs/changelog/`
   - Document all significant changes you make
   - Use descriptive language for future developers

4. **Maintain descriptive commit messages**
   - Start with the type of change: `feat:`, `fix:`, `docs:`, `refactor:`, etc.
   - Keep the first line under 50 characters
   - Include detailed explanation in the commit body if needed
   - Example: `feat: add MQTT support for pump control` or `fix: correct electrode positioning offset calculation`

5. **Track major milestones**
   - Update the root [README.md](../README.md) with version numbering
   - Document major releases and features
   - Keep version history organized and accessible

## Workflow for New Contributions

1. Create a feature branch for your work
2. Make your changes with clear, atomic commits
3. Document changes in your personal changelog folder
4. Update contributor information if needed
5. Create a pull request with a clear description
6. Ensure all tests pass before merging

## Version Numbering

Major version releases should be documented in the root [README.md](../README.md) using semantic versioning (MAJOR.MINOR.PATCH).

## Contributors

**Iliya**
- Original setup with Arduino for OTFlex and JSON workflow

**Alan Yang** (September 2025 - December 2025)
- OT2 setup
- MQTT IoT server
- 12VDC and 120VAC power tower

**Gavin Tranquilino** (January 2026 - April 2026)
- Monorepo setup
- Major documentation
- Iliya and Alan codebase merge
- Main Jupyter notebook setup with single cell step definitions and IoT MQTT management

---

For detailed usage instructions, see [USAGE.md](./USAGE.md).
For architecture details, see [ARCHITECTURE.md](./architecture/ARCHITECTURE.md).
