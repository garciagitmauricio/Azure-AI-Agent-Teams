# HR Policy Assistant – Minimal Deployment Guide (Microsoft 365 Agents Toolkit)

This README focuses ONLY on the essential steps to package and deploy the app to Microsoft Teams using the Microsoft 365 Agents Toolkit (toolkit-driven manifest templating + validation + packaging). All other architectural or future feature details are intentionally omitted per request.

# Watch the Video for Step by Step Configuration

[![Video Title](https://img.youtube.com/vi/HU5sAsD1DYw/0.jpg)](https://www.youtube.com/watch?v=HU5sAsD1DYw)
---
## Overview of Required Artifacts
| File | Purpose |
|------|---------|
| `appPackage/manifest.template.json` | Manifest template with placeholders (`${APP_VERSION}`, `${APP_ID}`, etc.). |
| `env/.env.dev` | Environment variable values used to substitute placeholders. |
| `m365agents.yml` | Toolkit configuration mapping environment -> template -> output paths. |
| `generate_icons.py` | Script that produces `color.png` (192x192) and `outline.png` (32x32, transparent). |
| `appPackage/color.png` | Color icon (added to package). |
| `appPackage/outline.png` | Outline icon (added to package). |

---
## 1. Prerequisites
1. Node.js (LTS) + npm
2. Python 3.10+ (only needed if you regenerate icons or run the Flask app)
3. Permission in your Microsoft 365 tenant to upload custom apps
4. Deployed (or reachable) web endpoint that serves your tab content (`APP_BASE_URL`)

---
## 2. Install Toolkit Locally (Recommended Project-Scoped Install)
```powershell
npm init -y  # if no package.json yet
npm install --save-dev @microsoft/m365agentstoolkit-cli
```
Invoke via the exposed binary name:
```powershell
npx atk --help
```

Global install (optional):
```powershell
npm install -g @microsoft/m365agentstoolkit-cli
atk --version
```

---
## 3. Create / Update Icons
Regenerate both icons (writes to `appPackage/`):
```powershell
python generate_icons.py
```
Result:
- `appPackage/color.png`
- `appPackage/outline.png` (transparent background confirmed)

---
## 4. Prepare the Manifest Template
`appPackage/manifest.template.json` contains placeholder tokens.
Key placeholders currently used:
- `${APP_VERSION}`
- `${APP_ID}` (a GUID – DO NOT CHANGE unless you want a new Teams app identity)
- `${APP_BASE_URL}` (root URL of your hosted web app)
- `${HOST_DOMAIN}` (domain portion used in `validDomains`)

Example excerpt:
```json
"version": "${APP_VERSION}",
"id": "${APP_ID}",
"validDomains": ["${HOST_DOMAIN}"]
```

---
## 5. Provide Environment Values (`env/.env.dev`)
Example current contents:
```bash
APP_ID=f47ac10b-58cc-4372-a567-0e02b2c3d479
APP_VERSION=1.2
APP_BASE_URL=https://<your-app-service>.azurewebsites.net
HOST_DOMAIN=<your-app-service>.azurewebsites.net
```
Edit `APP_VERSION` whenever you need to upload an updated package (Teams requires version bump).

---
## 6. Toolkit Configuration (`m365agents.yml`)
Current minimal config:
```yaml
version: 1.0
project:
  name: hr-policy-assistant
  templateFolder: appPackage
  manifestFile: appPackage/manifest.template.json

environments:
  dev:
    envFile: ./env/.env.dev
    output:
      manifestFile: appPackage/build/manifest.dev.json
      packageZipFile: appPackage/build/appPackage.dev.zip
```
Add additional environments (e.g., `prod`) by duplicating the block with a new env name + new `.env` file.

---
## 7. Validate the Resolved Manifest
Substitute placeholders and validate:
```powershell
npx atk validate --manifest-file appPackage/manifest.template.json --env dev
```
Alternatively validate the generated manifest after packaging (see next section).

---
## 8. Package the Teams App
Generate the ZIP (also produces the resolved manifest):
```powershell
npx atk package --env dev
```
Outputs:
- Resolved manifest: `appPackage/build/manifest.dev.json`
- Package ZIP: `appPackage/build/appPackage.dev.zip`

(Optional) Copy/rename for distribution:
```powershell
Copy-Item appPackage/build/appPackage.dev.zip dist/HRPolicyAssistant-v1.2.zip -Force
```
If `dist` doesn’t exist:
```powershell
New-Item -ItemType Directory dist | Out-Null
```

---
## 9. Upload to Teams
1. Open https://dev.teams.microsoft.com/ (Developer Portal)
2. Apps → Import App → Select the ZIP (`appPackage.dev.zip` or renamed copy)
3. Review → Save → Preview in Teams (or Distribute if moving to org-wide)

If the Developer Portal caches an icon or manifest field, bump `APP_VERSION` and re-package.

---
## 10. Version Bump Workflow
When making any change users must see in Teams:
1. Increment `APP_VERSION` in `env/.env.dev` (e.g., 1.2 → 1.2.1)
2. Re-run:
   ```powershell
   npx atk package --env dev
   ```
3. Upload new ZIP.

Tip: Keep a simple changelog or tag Git commits with the manifest version.

---
## 11. Quick One-Page Reference
```powershell
# 1. (Once) Install toolkit
npm install --save-dev @microsoft/m365agentstoolkit-cli

# 2. Regenerate icons (optional)
python generate_icons.py

# 3. Edit env/.env.dev (APP_VERSION, APP_BASE_URL etc.)

# 4. Validate
npx atk validate --manifest-file appPackage/manifest.template.json --env dev

# 5. Package
npx atk package --env dev

# 6. (Optional) Copy ZIP
Copy-Item appPackage/build/appPackage.dev.zip dist/HRPolicyAssistant-v1.2.zip -Force

# 7. Upload via Developer Portal
```

---
## 12. Adding Another Environment (Example: prod)
1. Create `env/.env.prod` with production values.
2. Append to `m365agents.yml`:
   ```yaml
   prod:
     envFile: ./env/.env.prod
     output:
       manifestFile: appPackage/build/manifest.prod.json
       packageZipFile: appPackage/build/appPackage.prod.zip
   ```
3. Package:
   ```powershell
   npx atk package --env prod
   ```

---
## 13. Troubleshooting (Essentials Only)
| Issue | Check |
|-------|-------|
| Upload rejected | Did you bump `APP_VERSION`? |
| Icons not updating | Teams cache → increment version again |
| Domain error | `HOST_DOMAIN` must match site host; ensure in `validDomains` |
| CLI not found | Use `npx atk ...` or reinstall dev dependency |

---
## 14. Minimal Change Flow Summary
Edit code / icons → bump `APP_VERSION` → `npx atk package --env dev` → upload ZIP.

That’s all that’s required for deployment with the toolkit.

---
*End of minimal guide.*

