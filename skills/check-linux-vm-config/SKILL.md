# /check-linux-vm-config

Check Linux VM YAML configuration against `rules/linux-vm-checks.yaml`.

## Steps

1. Run the check:
   ```bash
   python3 skills/check-linux-vm-config/check_linux_vm_config.py <vm.yaml>
   ```

2. Report findings to the user

## Rules

- `rules/linux-vm-checks.yaml` — defines all required settings

## Output Sections

- SEVERITY: based on critical issue count
- Table: per-setting PASS/FAIL/WARN
- RECOMMENDATION: list of issues with details
- SUMMARY: one-line verdict
