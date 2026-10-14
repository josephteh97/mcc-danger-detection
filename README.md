# Danger-Zone Pole Digital Twin

This is the Phase 1 digital twin of the danger-zone pit alarm pole. It is a set of Docker containers on one Linux PC that stands in for the whole pole:
- a simulated site and camera
- a sandbox playing the Orin AI box
- an emulator for every device and cable

The real alarm software (`app/`) runs inside the Orin sandbox unchanged.

**Status: Step 1 (specification).** The specs and the change proposal live in `openspec/changes/add-digital-twin-phase1/`:

- `proposal.md`: why, what changes, and the 11 capabilities
- `design.md`: architecture, decisions, deviations from the guide, and open questions
- `specs/<capability>/spec.md`: requirements and acceptance scenarios, including checks V01 to V34
- `tasks.md`: the implementation checklist for Step 2 (build) and Step 3 (remote access)

```bash
openspec list                                       # the active change
openspec show add-digital-twin-phase1               # read the proposal
openspec validate add-digital-twin-phase1 --strict  # check the specs
```

Setup, run and remote-access instructions will be added in Steps 2 and 3.
