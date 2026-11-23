## Highlights
- **🔌 Ready for Alma+ 3.0.** The task bridge (which hands your Alma+ tasks to Notion and Google Calendar) now accepts Alma+ 3.0's new fixed extension ID, so task sync keeps working after you update Alma+.

## Changes
- `install_task_bridge.sh` now allows both Alma+ 3.0's ID (`neganneopojdmfhpamgaonpcaiabgooc`) and the older one, so it works before and after the Alma+ update.
- No extension ID needs to be typed in anymore for Alma+ 3.0 and newer.

## How to update
1. Download this version (or `git pull`).
2. In the `alma_sync` folder, run `./install_task_bridge.sh` once.
3. In Chrome, open the Alma+ menu and press **Sync now** under Notion & Google Calendar to check it says "Synced".
