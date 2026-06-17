# How to build and ship StartGuard
Plain-English walkthrough — no experience needed.

---

## Before you start

Make sure you have these installed (you confirmed you do):
- Python + PyInstaller
- Inno Setup
- Git / GitHub

And make sure you're working from the correct folder:
```
C:\Users\YourUsername\Desktop\Project\SmartGuard\SmartGuard v1\SmartGuard
```

---

## Step 1 — Update the two paths in the Inno Setup script

Open `startguard_installer.iss` in Notepad (or any text editor).

Find this line near the top:
```
#define SourceDir "C:\Users\YourUsername\Desktop\..."
```

Replace `YourUsername` with your actual Windows username. Same for the `OutputDir` line just below it.

**How to find your username:** Open File Explorer, click on "This PC", then open the C: drive, then Users — your username is the folder name in there.

Save the file when done.

---

## Step 2 — Copy the spec and .iss files into your project

Put both files directly inside your project root folder:
```
SmartGuard\
  startguard.spec          ← put it here
  startguard_installer.iss ← put it here
  main.py
  main_window.py
  ...
```

---

## Step 3 — Open a terminal in your project folder

1. Open File Explorer and navigate to your project folder
2. Click the address bar at the top (where it shows the path)
3. Type `cmd` and press Enter
4. A black terminal window opens, already pointed at your project folder

---

## Step 4 — Run PyInstaller to build the app

In the terminal, type this exactly and press Enter:
```
pyinstaller startguard.spec
```

This will take 1–3 minutes. You'll see a lot of text scrolling by — that's normal.

**When it's done you should see:**
```
Building EXE from EXE-00.toc completed successfully.
```

**If it says something about a missing module**, paste the error here and we'll fix it together.

When it finishes, a new folder called `dist` will appear in your project folder.
Inside it: `dist\StartGuard\StartGuard.exe` — that's your built app.

---

## Step 5 — Test the built app before packaging

Before making the installer, run the .exe directly:

1. Navigate to `dist\StartGuard\`
2. Double-click `StartGuard.exe`
3. The UAC prompt should appear asking for admin rights — click Yes
4. StartGuard should open normally

If it opens fine, move on. If it crashes immediately, let me know what error appears.

---

## Step 6 — Build the installer with Inno Setup

1. Open **Inno Setup Compiler** (search for it in the Start menu)
2. Go to **File > Open**
3. Navigate to your project folder and open `startguard_installer.iss`
4. Press **F9** (or go to **Build > Compile**)

This takes about 30 seconds.

When done, your installer will appear at:
```
SmartGuard\Output\StartGuard_Setup_v0.9.0.exe
```

---

## Step 7 — Test the installer on your own PC first

1. Run `StartGuard_Setup_v0.9.0.exe`
2. Follow the install wizard
3. Confirm StartGuard appears in **Add or Remove Programs** (search for it in Windows settings)
4. Confirm the Start menu shortcut works
5. Open StartGuard and check everything works as expected

Work through the deployment testing checklist at this stage.

---

## Step 8 — Test on a second machine (very important)

Your own PC has Python, PyQt6, and everything else installed — so the app will work there even if something is missing from the bundle. A second machine with none of that installed is the real test.

If you have a second PC, or can borrow one, install StartGuard there and confirm it runs. If it crashes, it usually means a hidden import is missing from the spec file — paste the error and we'll fix it.

---

## Step 9 — Upload to GitHub

Once the installer passes testing:

1. Open a terminal in your project folder
2. Run these commands one at a time:
```
git add .
git commit -m "Release v0.9.0"
git tag v0.9.0
git push
git push --tags
```

Then go to your GitHub repo in a browser:
1. Click **Releases** on the right side
2. Click **Create a new release**
3. Select the `v0.9.0` tag you just pushed
4. Set the title to `StartGuard v0.9.0`
5. Upload `StartGuard_Setup_v0.9.0.exe` as the release asset
6. Write a short description of what StartGuard does
7. Click **Publish release**

---

## Checklist phase mapping

| Build step | Checklist phase |
|------------|----------------|
| Step 4 (PyInstaller) | Phase 1 — Build & package |
| Step 5 (test .exe) | Phase 1 + Phase 3 |
| Step 6 (Inno Setup) | Phase 1 |
| Step 7 (install on your PC) | Phase 2 + Phase 3 + Phase 4 + Phase 5 + Phase 6 |
| Step 8 (second machine) | Phase 2 — most important test |
| Uninstall test | Phase 7 |

---

## Common problems and fixes

**"ModuleNotFoundError" on launch after building**
A Python module wasn't bundled. Paste the error — we'll add it to `hiddenimports` in the spec file and rebuild.

**App opens then immediately closes**
Usually means an unhandled crash at startup. Temporarily change `console=False` to `console=True` in the spec file, rebuild, and launch from terminal — you'll see the actual error.

**Inno Setup says it can't find the source files**
The `SourceDir` path in the .iss file is wrong. Double-check your username and the folder structure.

**VirusTotal flags the installer**
This is a known false positive with PyInstaller bundles. It doesn't mean the app is malicious. Note which antivirus engines flagged it (usually 2–5 out of 70+) and mention it on your download page so users aren't alarmed. Most major engines (Windows Defender, Malwarebytes) will show clean.
