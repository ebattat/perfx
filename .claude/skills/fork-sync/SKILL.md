# /fork-sync

Sync the local fork (origin) with upstream after a merge.

## Steps

1. Fetch latest from upstream:
   ```bash
   git fetch upstream
   ```

2. Merge upstream into main:
   ```bash
   git merge upstream/main
   ```

3. Push to origin:
   ```bash
   git push origin main
   ```

## Notes

- Run this after every merged PR on `redhat-performance/perfx`
- Switch to `main` first if not already on it
- If there are conflicts, resolve them before pushing to origin
