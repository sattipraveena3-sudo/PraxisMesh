# Contributing

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,openai]"
make test
make lint
```

## Trust-kernel changes

Changes to policies, tools, verifiers, approval state or audit logic require:

1. a threat-model update when the capability or trust boundary changes;
2. positive and negative tests;
3. an architecture decision record for a durable design change;
4. backward-compatibility notes for persisted run data;
5. evidence that the planner cannot bypass the new control.

Keep pull requests focused. Never commit credentials, `.env`, runtime databases or generated workspaces.

