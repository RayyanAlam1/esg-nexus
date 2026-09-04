## Summary

<!-- What changes and why. Link the issue: Closes #… -->

## Type of change

- [ ] Bug fix
- [ ] New feature (metric, framework, agent, connector, report section, rule)
- [ ] Refactor / maintenance
- [ ] Documentation

## Checklist

- [ ] Backend: `ruff check .` and `pytest` pass locally
- [ ] Frontend: `npx tsc --noEmit` and `npm run build` pass locally
- [ ] Model changes include an Alembic revision
- [ ] New metrics/frameworks are configuration (YAML) with evidence references, not hard-coded
- [ ] No ESG figures are invented; missing data is represented as `Data unavailable`
- [ ] Documentation updated (`docs/` and guides where relevant)
