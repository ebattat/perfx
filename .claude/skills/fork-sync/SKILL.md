# /fork-sync

Sync the local fork (origin) with upstream after a merge.

## Steps

1. Switch to main branch:
   ```bash
   git checkout main
   ```

2. Fetch latest from upstream:
   ```bash
   git fetch upstream
   ```

3. Merge upstream into main:
   ```bash
   git merge upstream/main
   ```

4. Push to origin:
   ```bash
   git push origin main
   ```

5. Confirm sync:
   ```bash
   git log --oneline -5
   git remote -v
   ```

## Notes

- Run this after every merged PR on `redhat-performance/perfx`
- If there are conflicts, resolve them before pushing to origin
